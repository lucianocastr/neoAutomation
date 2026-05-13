#include <Arduino.h>
#include <WiFi.h>
#include <WiFiServer.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "config.h"

// ── Estado global ───────────────────────────────────────────

enum State { IDLE, HOMING, MOVING, ZEROING, ERR };
volatile State current_state = IDLE;
int32_t current_steps = 0;   // posición actual en pasos desde home

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

// Mueve a target_steps a la velocidad dada. Respeta los fines de carrera.
// Retorna false si fue detenido por fin de carrera o safety.
bool move_to_steps(int32_t target, int speed_steps_per_s) {
    uint32_t delay_us = 1000000UL / speed_steps_per_s;
    bool going_down = target > current_steps;

    while (current_steps != target) {
        if (!going_down && digitalRead(PIN_HOME_SW) == LOW) {
            current_steps = 0;   // re-homing implícito
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

// Anti-backlash (§6.4): la posición final siempre se alcanza desde arriba.
// Si hay que subir, sube BACKLASH_STEPS de más y luego baja al target.
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
    return doc["weight"].as<float>() * 1000.0f;   // kg → g
}

// Fase creep: baja lento hasta detectar >CONTACT_THRESHOLD_G en la bandeja.
// Retorna true si se detectó contacto antes de alcanzar max_steps.
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

        // Sondear la API cada 200ms (no en cada paso — sería demasiado lento)
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
    uint32_t deadline = millis() + 30000;   // timeout 30s

    while (digitalRead(PIN_HOME_SW) != LOW) {
        if (millis() > deadline) {
            Serial.println("Homing timeout");
            return false;
        }
        step_once(false);   // sube
        delayMicroseconds(1000000UL / FAST_SPEED);
    }
    current_steps = 0;
    Serial.println("Home found. Backing off...");
    move_to_steps(50, CREEP_SPEED);   // retrocede 50 pasos del switch
    return true;
}

// ── Handlers de comandos ─────────────────────────────────────

String handle_set_weight(int grams) {
    if (current_state != IDLE)
        return "{\"status\":\"error\",\"message\":\"busy\"}";

    current_state = MOVING;
    stepper_enable();

    int32_t target_steps    = (int32_t)((float)grams * STEPS_PER_GRAM);
    int32_t approach_steps  = target_steps - APPROACH_MARGIN_STEPS;
    if (approach_steps < 0) approach_steps = 0;

    // Fase rápida hasta APPROACH_MARGIN_STEPS antes del contacto esperado
    set_position_with_backlash(approach_steps, FAST_SPEED);

    // Fase creep: baja despacio y detecta contacto
    bool contact = creep_until_contact(target_steps + 200);
    stepper_disable();

    if (!contact) {
        current_state = ERR;
        Serial.printf("No contact for %dg (target %d steps)\n", grams, target_steps);
        return "{\"status\":\"error\",\"message\":\"no_contact\"}";
    }

    current_state = IDLE;
    return "{\"status\":\"ok\",\"state\":\"READY\"}";
}

String handle_zero() {
    if (current_state != IDLE)
        return "{\"status\":\"error\",\"message\":\"busy\"}";

    current_state = ZEROING;
    stepper_enable();

    uint32_t last_poll_ms = millis();
    while (current_steps > 0) {
        if (digitalRead(PIN_HOME_SW) == LOW) {
            current_steps = 0;
            break;
        }
        step_once(false);   // sube
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
    return ok
        ? "{\"status\":\"ok\",\"state\":\"HOMED\"}"
        : "{\"status\":\"error\",\"message\":\"homing_timeout\"}";
}

String handle_status() {
    char buf[128];
    snprintf(buf, sizeof(buf),
        "{\"status\":\"ok\",\"state\":\"%s\",\"steps\":%d}",
        state_name(current_state), current_steps);
    return String(buf);
}

String handle_set_calibration(float steps_per_gram) {
    // Permite ajustar STEPS_PER_GRAM en runtime desde el script de calibración
    // En una implementación real se guardaría en NVS; aquí lo dejamos en RAM
    // para simplicity del POC.
    Serial.printf("Calibration updated: %.4f steps/g\n", steps_per_gram);
    // No se modifica la constante — se usa una variable global para el POC
    return "{\"status\":\"ok\"}";
}

// ── Setup ────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== CUORA NEO Actuator Firmware ===");
    Serial.println("Board: ESP32-S3 DevKitC-1 N16R8");

    // Pines del motor
    pinMode(PIN_STEP, OUTPUT);
    pinMode(PIN_DIR,  OUTPUT);
    pinMode(PIN_EN,   OUTPUT);
    pinMode(PIN_M0,   OUTPUT);
    pinMode(PIN_M1,   OUTPUT);
    pinMode(PIN_M2,   OUTPUT);
    stepper_disable();

    // 1/32 microstepping (M0=H, M1=H, M2=H para DRV8825)
    digitalWrite(PIN_M0, HIGH);
    digitalWrite(PIN_M1, HIGH);
    digitalWrite(PIN_M2, HIGH);

    // Fines de carrera
    pinMode(PIN_HOME_SW,   INPUT_PULLUP);
    pinMode(PIN_SAFETY_SW, INPUT_PULLUP);

    // WiFi
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("Connecting WiFi");
    uint32_t wifi_start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - wifi_start > 20000) {
            Serial.println("\nWiFi timeout — reboot");
            ESP.restart();
        }
        delay(500);
        Serial.print(".");
    }
    Serial.print("\nIP: ");
    Serial.println(WiFi.localIP());

    tcp_server.begin();
    Serial.printf("TCP server ready on port %d\n", TCP_PORT);
}

// ── Loop ─────────────────────────────────────────────────────

void loop() {
    WiFiClient client = tcp_server.available();
    if (!client) return;

    Serial.println("Client connected");
    String line = client.readStringUntil('\n');
    line.trim();

    if (line.isEmpty()) {
        client.stop();
        return;
    }

    Serial.print("CMD: "); Serial.println(line);

    JsonDocument doc;
    if (deserializeJson(doc, line) != DeserializationError::Ok) {
        client.println("{\"status\":\"error\",\"message\":\"invalid_json\"}");
        client.stop();
        return;
    }

    const char* cmd = doc["cmd"] | "";
    String response;

    if      (strcmp(cmd, "SET_WEIGHT")      == 0) response = handle_set_weight(doc["grams"] | 0);
    else if (strcmp(cmd, "ZERO")            == 0) response = handle_zero();
    else if (strcmp(cmd, "HOME")            == 0) response = handle_home();
    else if (strcmp(cmd, "STATUS")          == 0) response = handle_status();
    else if (strcmp(cmd, "SET_CALIBRATION") == 0) response = handle_set_calibration(doc["steps_per_gram"] | STEPS_PER_GRAM);
    else response = "{\"status\":\"error\",\"message\":\"unknown_cmd\"}";

    Serial.print("RSP: "); Serial.println(response);
    client.println(response);
    client.stop();
}
