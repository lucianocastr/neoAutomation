#include <WiFi.h>
#include <USB.h>
#include <USBHIDKeyboard.h>
#include <ArduinoJson.h>

// ── Configuración ────────────────────────────────────────────
const char* WIFI_SSID = "CataNET-2.4G";
const char* WIFI_PASS = "RLOVCAA916";
const int   TCP_PORT  = 9999;

USBHIDKeyboard Keyboard;
WiFiServer     server(TCP_PORT);

// ── Mapeo teclas → USB HID (confirmado por teclado-fisico-NEO.jpeg) ──
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

// ── Enviar una tecla con press + release ─────────────────────
String send_key(const char* key_name) {
    // Caso 1: tecla nombrada (F2, ENTER, UP, etc.)
    uint8_t code = resolve_key(key_name);
    if (code != 0) {
        Keyboard.press(code);
        delay(80);
        Keyboard.releaseAll();
        return "{\"status\":\"ok\"}";
    }

    // Caso 2: dígito único — fila numérica superior (NO numpad)
    if (strlen(key_name) == 1 && key_name[0] >= '0' && key_name[0] <= '9') {
        Keyboard.print(key_name[0]);
        return "{\"status\":\"ok\"}";
    }

    // Caso 3: "00" → dos ceros
    if (strcmp(key_name, "00") == 0) {
        Keyboard.print('0');
        delay(50);
        Keyboard.print('0');
        return "{\"status\":\"ok\"}";
    }

    return "{\"status\":\"error\",\"msg\":\"unknown_key\"}";
}

// ── Setup ────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);

    // ── 1. WiFi y TCP server ANTES de aparecer como teclado ──
    // El kernel de la balanza puede colgarse si recibe un USB HID
    // device mientras su stack USB todavía está inicializándose.
    // Establecemos la red primero para tener control remoto antes
    // de tocar el USB de la balanza.
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("WiFi");
    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - t0 > 30000) {
            Serial.println("\nWiFi timeout — reboot");
            ESP.restart();
        }
        delay(500);
        Serial.print(".");
    }
    Serial.print("\nIP: ");
    Serial.println(WiFi.localIP());

    server.begin();
    Serial.printf("TCP server listo en :%d\n", TCP_PORT);

    // ── 2. Pausa antes de enumerar el HID ────────────────────
    // 8s es suficiente para que la balanza haya completado su boot
    // y el kernel esté en estado estable para recibir un HID device.
    Serial.println("Esperando estabilizacion del SO de la balanza...");
    delay(8000);

    // ── 3. Inicializar USB HID ────────────────────────────────
    USB.begin();
    Keyboard.begin();
    delay(1500);   // estabilizacion post-enumeracion
    Serial.println("USB HID keyboard ready");
}

// ── Loop ─────────────────────────────────────────────────────
void loop() {
    WiFiClient client = server.available();
    if (!client) return;

    String line = client.readStringUntil('\n');
    line.trim();
    Serial.print("CMD: "); Serial.println(line);

    if (line.isEmpty()) { client.stop(); return; }

    JsonDocument doc;
    if (deserializeJson(doc, line) != DeserializationError::Ok) {
        client.println("{\"status\":\"error\",\"msg\":\"invalid_json\"}");
        client.stop(); return;
    }

    const char* cmd = doc["cmd"] | "";
    String response;

    if (strcmp(cmd, "KEY_PRESS") == 0) {
        response = send_key(doc["key"] | "");
    } else if (strcmp(cmd, "STATUS") == 0) {
        response = "{\"status\":\"ok\",\"state\":\"IDLE\"}";
    } else {
        response = "{\"status\":\"error\",\"msg\":\"unknown_cmd\"}";
    }

    Serial.print("RSP: "); Serial.println(response);
    client.println(response);
    client.stop();
}
