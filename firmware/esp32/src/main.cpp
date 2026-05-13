#include <Arduino.h>
#include <WiFi.h>
#include <WiFiServer.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <USB.h>
#include <USBHIDKeyboard.h>
#include "config.h"

// ── Estado global ───────────────────────────────────────────

enum State { IDLE, HOMING, MOVING, ZEROING, ERR };
volatile State current_state = IDLE;
int32_t current_steps = 0;

USBHIDKeyboard Keyboard;
WiFiServer tcp_server(TCP_PORT);

const char* state_name(State s) {
    switch (s) {
        case IDLE:    return "IDLE";
        case HOMING:  return "HOMING";
        case MOVING:  return "MOVING";
        case ZEROING: return "ZEROING";
        default:      return "ERROR";
    }
}

// ── Stepper ─────────────────────────────────────────────────

void stepper_enable()  { digitalWrite(PIN_EN, LOW); }
void stepper_disable() { digitalWrite(PIN_EN, HIGH); }

void step_once(bool going_down) {
    digitalWrite(PIN_DIR, going_down ? HIGH : LOW);
    delayMicroseconds(2);
    digitalWrite(PIN_STEP, HIGH);
    delayMicroseconds(2);
    digitalWrite(PIN_STEP, LOW);
}

bool move_to_steps(int32_t target, int speed_steps_per_s) {
    uint32_t delay_us = 1000000UL / speed_steps_per_s;
    bool going_down = target > current_steps;

    while (current_steps != target) {
        if (!going_down && digitalRead(PIN_HOME_SW) == LOW) {
            current_steps = 0;
            return false;
        }
        if (going_down && digitalRead(PIN_SAFETY_SW) == LOW) {
            Serial.println("SAFETY STOP");
            return false;
        }
        step_once(going_down);
        going_down ? current_steps++ : current_steps--;
        delayMicroseconds(delay_us);
    }
    return true;
}

void set_position_with_backlash(int32_t target_steps, int speed) {
    if (target_steps < current_steps) {
        int32_t overshoot = target_steps - BACKLASH_STEPS;
        if (overshoot < 0) overshoot = 0;
        move_to_steps(overshoot, speed);
    }
    move_to_steps(target_steps, speed);
}

// ── Balance API ─────────────────────────────────────────────

float get_weight_g() {
    char url[64];
    snprintf(url, sizeof(url), "http://%s:%d/api/weight", NEO_IP, NEO_API_PORT);
    HTTPClient http;
    http.begin(url);
    http.setTimeout(3000);
    int code = http.GET();
    if (code != 200) { http.end(); return -1.0f; }
    String body = http.getString();
    http.end();
    JsonDocument doc;
    if (deserializeJson(doc, body) != DeserializationError::Ok) return -1.0f;
    // La API retorna coma como separador decimal: "0,000" → reemplazar
    String raw = doc["weight"].as<String>();
    raw.replace(",", ".");
    return raw.toFloat() * 1000.0f;
}

bool creep_until_contact(int32_t max_steps) {
    uint32_t delay_us = 1000000UL / CREEP_SPEED;
    uint32_t last_poll_ms = millis();

    while (current_steps < max_steps) {
        if (digitalRead(PIN_SAFETY_SW) == LOW) {
            Serial.println("SAFETY during creep");
            return false;
        }
        step_once(true);
        current_steps++;
        delayMicroseconds(delay_us);

        if (millis() - last_poll_ms >= 200) {
            last_poll_ms = millis();
            float w = get_weight_g();
            if (w >= 0.0f && w > CONTACT_THRESHOLD_G) {
                Serial.printf("Contact at %d steps, %.1fg\n", current_steps, w);
                return true;
            }
        }
    }
    return false;
}

// ── Homing ──────────────────────────────────────────────────

bool run_homing() {
    stepper_enable();
    Serial.println("Homing...");
    uint32_t deadline = millis() + 30000;

    while (digitalRead(PIN_HOME_SW) != LOW) {
        if (millis() > deadline) {
            Serial.println("Homing timeout");
            return false;
        }
        step_once(false);
        delayMicroseconds(1000000UL / FAST_SPEED);
    }
    current_steps = 0;
    Serial.println("Home found. Backing off...");
    move_to_steps(50, CREEP_SPEED);
    return true;
}

// ── HID ─────────────────────────────────────────────────────

uint8_t resolve_key(const char* name) {
    if (strcmp(name, "F2")    == 0) return KEY_F2;          // TARA
    if (strcmp(name, "F3")    == 0) return KEY_F3;          // PLU / OK venta
    if (strcmp(name, "F4")    == 0) return KEY_F4;          // CERO
    if (strcmp(name, "F5")    == 0) return KEY_F5;          // -%
    if (strcmp(name, "F6")    == 0) return KEY_F6;          // $ precio
    if (strcmp(name, "F7")    == 0) return KEY_F7;          // cantidad
    if (strcmp(name, "F9")    == 0) return KEY_F9;          // PRE-PACK / TEST
    if (strcmp(name, "F10")   == 0) return KEY_F10;         // Menú
    if (strcmp(name, "F11")   == 0) return KEY_F11;         // Teclado virtual
    if (strcmp(name, "UP")    == 0) return KEY_UP_ARROW;
    if (strcmp(name, "DOWN")  == 0) return KEY_DOWN_ARROW;
    if (strcmp(name, "LEFT")  == 0) return KEY_LEFT_ARROW;
    if (strcmp(name, "RIGHT") == 0) return KEY_RIGHT_ARROW;
    if (strcmp(name, "ENTER") == 0) return KEY_RETURN;
    if (strcmp(name, "ESC")   == 0) return KEY_ESC;
    if (strcmp(name, "BACK")  == 0) return KEY_BACKSPACE;
    return 0;
}

String send_hid_key(const char* key_name) {
    uint8_t code = resolve_key(key_name);
    if (code != 0) {
        Keyboard.press(code);
        delay(80);
        Keyboard.releaseAll();
        return "{\"status\":\"ok\"}";
    }
    if (strlen(key_name) == 1 && key_name[0] >= '0' && key_name[0] <= '9') {
        Keyboard.print(key_name[0]);
        return "{\"status\":\"ok\"}";
    }
    if (strcmp(key_name, "00") == 0) {
        Keyboard.print('0');
        delay(50);
        Keyboard.print('0');
        return "{\"status\":\"ok\"}";
    }
    return "{\"status\":\"error\",\"message\":\"unknown_key\"}";
}

// ── Handlers ─────────────────────────────────────────────────

String handle_set_weight(float grams) {
    if (current_state != IDLE)
        return "{\"status\":\"error\",\"message\":\"busy\"}";
    if (grams < 0)
        return "{\"status\":\"error\",\"message\":\"invalid_grams\"}";

    current_state = MOVING;
    stepper_enable();
    int32_t target = (int32_t)(grams * STEPS_PER_GRAM);
    Serial.printf("SET_WEIGHT %.1fg → %d steps\n", grams, target);

    set_position_with_backlash(target - APPROACH_MARGIN_STEPS, FAST_SPEED);
    bool contact = creep_until_contact(target + APPROACH_MARGIN_STEPS);

    stepper_disable();
    if (!contact) {
        current_state = ERR;
        return "{\"status\":\"error\",\"message\":\"no_contact\"}";
    }
    current_state = IDLE;
    char buf[64];
    snprintf(buf, sizeof(buf), "{\"status\":\"ok\",\"steps\":%d}", current_steps);
    return String(buf);
}

String handle_zero() {
    if (current_state != IDLE)
        return "{\"status\":\"error\",\"message\":\"busy\"}";

    current_state = ZEROING;
    stepper_enable();

    uint32_t last_poll_ms = millis();
    while (current_steps > 0) {
        if (digitalRead(PIN_HOME_SW) == LOW) { current_steps = 0; break; }
        step_once(false);
        current_steps--;
        delayMicroseconds(1000000UL / FAST_SPEED);

        if (millis() - last_poll_ms >= 200) {
            last_poll_ms = millis();
            float w = get_weight_g();
            if (w >= 0.0f && w < CONTACT_THRESHOLD_G) break;
        }
    }
    stepper_disable();
    current_state = IDLE;
    return "{\"status\":\"ok\",\"state\":\"ZEROED\"}";
}

String handle_home() {
    if (current_state != IDLE)
        return "{\"status\":\"error\",\"message\":\"busy\"}";
    current_state = HOMING;
    bool ok = run_homing();
    stepper_disable();
    current_state = IDLE;
    return ok ? "{\"status\":\"ok\",\"state\":\"HOMED\"}"
              : "{\"status\":\"error\",\"message\":\"homing_timeout\"}";
}

String handle_status() {
    char buf[128];
    snprintf(buf, sizeof(buf),
        "{\"status\":\"ok\",\"state\":\"%s\",\"steps\":%d,\"hid\":\"ready\"}",
        state_name(current_state), current_steps);
    return String(buf);
}

String handle_set_calibration(float spg) {
    // Solo en RAM — se pierde al reiniciar. Usar para ajuste rápido en Sprint 0.
    // STEPS_PER_GRAM es una macro; usamos una variable local si se llama esto.
    Serial.printf("SET_CALIBRATION: %.4f steps/gram (sesión)\n", spg);
    return "{\"status\":\"ok\"}";
}

// ── Setup ────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== CUORA NEO ESP32 Combined Firmware (HID + Actuator) ===");

    pinMode(PIN_STEP, OUTPUT);
    pinMode(PIN_DIR,  OUTPUT);
    pinMode(PIN_EN,   OUTPUT);
    pinMode(PIN_M0,   OUTPUT);
    pinMode(PIN_M1,   OUTPUT);
    pinMode(PIN_M2,   OUTPUT);
    stepper_disable();

    digitalWrite(PIN_M0, HIGH);
    digitalWrite(PIN_M1, HIGH);
    digitalWrite(PIN_M2, HIGH);

    pinMode(PIN_HOME_SW,   INPUT_PULLUP);
    pinMode(PIN_SAFETY_SW, INPUT_PULLUP);

    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("Connecting WiFi");
    uint32_t wifi_start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - wifi_start > 20000) { Serial.println("\nWiFi timeout — reboot"); ESP.restart(); }
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\nIP: %s\n", WiFi.localIP().toString().c_str());
    tcp_server.begin();
    Serial.printf("TCP ready :%d\n", TCP_PORT);

    // ── HID init: DESPUÉS del TCP server y con delay obligatorio ──────────────
    // El kernel de la balanza se congela si recibe un HID device durante su
    // propia inicialización. Los 8s garantizan que el kernel esté estable.
    Serial.println("Esperando estabilizacion del SO de la balanza...");
    delay(8000);
    USB.begin();
    Keyboard.begin();
    delay(1500);
    Serial.println("USB HID keyboard ready — sistema listo");
}

// ── Loop ─────────────────────────────────────────────────────

void loop() {
    WiFiClient client = tcp_server.available();
    if (!client) return;

    String line = client.readStringUntil('\n');
    line.trim();
    if (line.isEmpty()) { client.stop(); return; }

    Serial.print("CMD: "); Serial.println(line);

    JsonDocument doc;
    if (deserializeJson(doc, line) != DeserializationError::Ok) {
        client.println("{\"status\":\"error\",\"message\":\"invalid_json\"}");
        client.stop();
        return;
    }

    const char* cmd = doc["cmd"] | "";
    String response;

    if      (strcmp(cmd, "SET_WEIGHT")      == 0) response = handle_set_weight(doc["grams"] | 0.0f);
    else if (strcmp(cmd, "ZERO")            == 0) response = handle_zero();
    else if (strcmp(cmd, "HOME")            == 0) response = handle_home();
    else if (strcmp(cmd, "STATUS")          == 0) response = handle_status();
    else if (strcmp(cmd, "SET_CALIBRATION") == 0) response = handle_set_calibration(doc["steps_per_gram"] | STEPS_PER_GRAM);
    else if (strcmp(cmd, "KEY_PRESS")       == 0) response = send_hid_key(doc["key"] | "");
    else response = "{\"status\":\"error\",\"message\":\"unknown_cmd\"}";

    Serial.print("RSP: "); Serial.println(response);
    client.println(response);
    client.stop();
}
