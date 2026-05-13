#include <Arduino.h>
#include <WiFi.h>
#include <WiFiServer.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "config.h"

// ── Estado global ───────────────────────────────────────────

enum State { IDLE, HOMING, MOVING, ZEROING, PICKING, LIFTING, ERR };
volatile State current_state = IDLE;
int32_t current_steps = 0;
int8_t  tray_count    = 0;   // pesas actualmente sobre la bandeja

WiFiServer tcp_server(TCP_PORT);

static const float slot_heights_mm[NUM_SLOTS] = {
    SLOT_HEIGHT_MM_0,
    SLOT_HEIGHT_MM_1,
    SLOT_HEIGHT_MM_2,
    SLOT_HEIGHT_MM_3
};

const char* state_name(State s) {
    switch (s) {
        case IDLE:    return "IDLE";
        case HOMING:  return "HOMING";
        case MOVING:  return "MOVING";
        case ZEROING: return "ZEROING";
        case PICKING: return "PICKING";
        case LIFTING: return "LIFTING";
        default:      return "ERROR";
    }
}

// ── Conversión posición ─────────────────────────────────────

// Milímetros de desplazamiento hacia abajo desde HOME a pasos.
// 6400 steps/rev ÷ 1.25mm/rev = 5120 steps/mm. Calibrar en Sprint 0.
int32_t mm_to_steps(float mm) {
    return (int32_t)(mm * (6400.0f / 1.25f));
}

int32_t slot_to_steps(int slot) {
    return mm_to_steps(HOME_HEIGHT_MM - slot_heights_mm[slot]);
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

// ── Electroimán ─────────────────────────────────────────────

void magnet_on() {
    digitalWrite(PIN_MAGNET, HIGH);
    delay(MAGNET_ON_MS);
}

void magnet_off() {
    digitalWrite(PIN_MAGNET, LOW);
    delay(MAGNET_OFF_MS);
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
    return doc["weight"].as<float>() * 1000.0f;
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

// ── Handlers ─────────────────────────────────────────────────

// Coloca la pesa del slot indicado sobre la bandeja.
String handle_pick(int slot) {
    if (slot < 0 || slot >= NUM_SLOTS)
        return "{\"status\":\"error\",\"message\":\"invalid_slot\"}";
    if (current_state != IDLE)
        return "{\"status\":\"error\",\"message\":\"busy\"}";

    current_state = PICKING;
    stepper_enable();
    Serial.printf("PICK slot %d (%.0fmm)\n", slot, slot_heights_mm[slot]);

    // Ir al slot
    set_position_with_backlash(slot_to_steps(slot), FAST_SPEED);

    // Energizar imán
    magnet_on();

    // Subir para sacar la pesa del peg
    int32_t clear = current_steps - mm_to_steps(PEG_CLEAR_MM);
    if (clear < 0) clear = 0;
    move_to_steps(clear, CREEP_SPEED);

    // Bajar rápido al margen sobre la bandeja y hacer creep
    set_position_with_backlash(mm_to_steps(HOME_HEIGHT_MM - T_BANDEJA_MM - 30.0f), FAST_SPEED);
    bool contact = creep_until_contact(mm_to_steps(HOME_HEIGHT_MM - T_BANDEJA_MM + 50.0f));

    // Soltar la pesa
    magnet_off();

    run_homing();
    stepper_disable();

    if (!contact) {
        current_state = ERR;
        return "{\"status\":\"error\",\"message\":\"no_tray_contact\"}";
    }

    tray_count++;
    current_state = IDLE;
    char buf[64];
    snprintf(buf, sizeof(buf), "{\"status\":\"ok\",\"tray_count\":%d}", tray_count);
    return String(buf);
}

// Levanta la pesa superior de la bandeja y la deposita en el slot indicado.
String handle_lift(int slot) {
    if (slot < 0 || slot >= NUM_SLOTS)
        return "{\"status\":\"error\",\"message\":\"invalid_slot\"}";
    if (current_state != IDLE)
        return "{\"status\":\"error\",\"message\":\"busy\"}";
    if (tray_count <= 0)
        return "{\"status\":\"error\",\"message\":\"tray_empty\"}";

    current_state = LIFTING;
    stepper_enable();
    Serial.printf("LIFT → slot %d (%.0fmm)\n", slot, slot_heights_mm[slot]);

    // Bajar al margen y hacer creep hasta la pesa
    set_position_with_backlash(mm_to_steps(HOME_HEIGHT_MM - T_BANDEJA_MM - 30.0f), FAST_SPEED);
    bool contact = creep_until_contact(mm_to_steps(HOME_HEIGHT_MM - T_BANDEJA_MM + 50.0f));

    if (!contact) {
        stepper_disable();
        current_state = ERR;
        return "{\"status\":\"error\",\"message\":\"no_weight_on_tray\"}";
    }

    // Energizar imán con tiempo extra para sujetar hasta 2kg
    magnet_on();
    delay(400);

    // Despegar de la bandeja
    int32_t lift_off = current_steps - mm_to_steps(PEG_CLEAR_MM);
    if (lift_off < 0) lift_off = 0;
    move_to_steps(lift_off, CREEP_SPEED);

    // Trasladar al slot
    set_position_with_backlash(slot_to_steps(slot), FAST_SPEED);

    // Bajar levemente para enganchar el peg
    move_to_steps(slot_to_steps(slot) + mm_to_steps(PEG_ENGAGE_MM), CREEP_SPEED);

    // Soltar — la pesa queda en el peg
    magnet_off();

    // Subir para confirmar desenganche del imán
    move_to_steps(slot_to_steps(slot) - mm_to_steps(PEG_CLEAR_MM), CREEP_SPEED);

    run_homing();
    stepper_disable();

    tray_count--;
    current_state = IDLE;
    char buf[64];
    snprintf(buf, sizeof(buf), "{\"status\":\"ok\",\"tray_count\":%d}", tray_count);
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
        "{\"status\":\"ok\",\"state\":\"%s\",\"steps\":%d,\"tray_count\":%d}",
        state_name(current_state), current_steps, tray_count);
    return String(buf);
}

// Fuerza tray_count=0. Llamar cuando la bandeja se despejó manualmente.
String handle_reset_magazine() {
    tray_count = 0;
    magnet_off();
    return "{\"status\":\"ok\",\"tray_count\":0}";
}

// ── Setup ────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== CUORA NEO Actuator-Electroiman Firmware ===");

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

    // Electroimán — IRLZ44N, compatible con 3.3V lógico
    pinMode(PIN_MAGNET, OUTPUT);
    magnet_off();

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
    Serial.printf("TCP ready :%d — %d slots, HOME=%.0fmm, BANDEJA=%.0fmm\n",
                  TCP_PORT, NUM_SLOTS, HOME_HEIGHT_MM, T_BANDEJA_MM);
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

    if      (strcmp(cmd, "PICK")            == 0) response = handle_pick(doc["slot"] | -1);
    else if (strcmp(cmd, "LIFT")            == 0) response = handle_lift(doc["slot"] | -1);
    else if (strcmp(cmd, "MAGNET_ON")       == 0) { magnet_on();  response = "{\"status\":\"ok\"}"; }
    else if (strcmp(cmd, "MAGNET_OFF")      == 0) { magnet_off(); response = "{\"status\":\"ok\"}"; }
    else if (strcmp(cmd, "RESET_MAGAZINE")  == 0) response = handle_reset_magazine();
    else if (strcmp(cmd, "ZERO")            == 0) response = handle_zero();
    else if (strcmp(cmd, "HOME")            == 0) response = handle_home();
    else if (strcmp(cmd, "STATUS")          == 0) response = handle_status();
    else response = "{\"status\":\"error\",\"message\":\"unknown_cmd\"}";

    Serial.print("RSP: "); Serial.println(response);
    client.println(response);
    client.stop();
}
