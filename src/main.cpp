#include <Arduino.h>
#include "esp_camera.h"
#include "esp_sleep.h"
#include <WiFi.h>
#include <HTTPClient.h>

#include "board_config.h"
#include "app_httpd.h"

const char *ssid     = "ASUS2";
const char *password = "PetrSmolik";

#define PIR_PIN          3
#define PIR_NOTIFY_URL   "http://192.168.0.65:8080/motion"
#define PIR_IDLE_URL     "http://192.168.0.65:8080/idle"
#define IDLE_TIMEOUT_MS  100000   // 30s bez pohybu → sleep

static void goToSleep() {
  Serial.println("No motion, going to sleep");
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(PIR_IDLE_URL);
    http.addHeader("Content-Type", "application/json");
    http.POST("{}");
    http.end();
  }
  esp_sleep_enable_ext1_wakeup(1ULL << PIR_PIN, ESP_EXT1_WAKEUP_ANY_HIGH);
  esp_deep_sleep_start();
}

static void sleepMonitorTask(void *) {
  uint32_t lastMotion = millis();
  bool lastState = false;

  for (;;) {
    bool state = digitalRead(PIR_PIN) == HIGH;

    if (state != lastState) {
      Serial.printf("PIR: %s\n", state ? "pohyb" : "klid");
      lastState = state;
    }

    if (state) {
      lastMotion = millis();
      Serial.printf("PIR: pohyb (sleep timer resetovan)\n");
    } else {
      uint32_t idle = millis() - lastMotion;
      Serial.printf("PIR: klid uz %lu s (sleep za %lu s)\n",
                    idle / 1000, (IDLE_TIMEOUT_MS - idle) / 1000);
    }

    if (millis() - lastMotion >= IDLE_TIMEOUT_MS) {
      goToSleep();
    }
    vTaskDelay(1000 / portTICK_PERIOD_MS);
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);
  Serial.setDebugOutput(true);
  Serial.println();

  pinMode(PIR_PIN, INPUT_PULLDOWN);

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 23000000;
  config.frame_size   = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location  = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count     = 1;

  if (psramFound()) {
    config.jpeg_quality = 10;
    config.fb_count     = 2;
    config.grab_mode    = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size  = FRAMESIZE_SVGA;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  s->set_framesize(s, FRAMESIZE_VGA);

  WiFi.begin(ssid, password);
  WiFi.setSleep(false);

  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");

  startCameraServer();

  // Notify RPi — woke up because of motion
  {
    HTTPClient http;
    http.begin(PIR_NOTIFY_URL);
    http.addHeader("Content-Type", "application/json");
    http.POST("{\"motion\":true}");
    http.end();
  }
  
  Serial.println("PIR: cekam na kalibraci senzoru...");
  delay(5000);
  Serial.println("PIR: pripraveno");
  xTaskCreate(sleepMonitorTask, "sleep_mon", 4096, NULL, 1, NULL);

  Serial.printf("Stream: http://%s:81/stream\n", WiFi.localIP().toString().c_str());
}

void loop() {
  delay(10000);
}
