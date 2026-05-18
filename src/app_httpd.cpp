#include "Arduino.h"
#include "esp_http_server.h"
#include "esp_camera.h"
#include "sdkconfig.h"

#define PART_BOUNDARY "123456789000000000000987654321"
static const char *_STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char *_STREAM_BOUNDARY     = "\r\n--" PART_BOUNDARY "\r\n";
static const char *_STREAM_PART         = "Content-Type: image/jpeg\r\nContent-Length: %u\r\nX-Timestamp: %d.%06d\r\n\r\n";

static httpd_handle_t camera_httpd = NULL;
static httpd_handle_t stream_httpd = NULL;

static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t *fb = NULL;
  esp_err_t res;
  char part_buf[128];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      log_e("Camera capture failed");
      break;
    }

    size_t hlen = snprintf(part_buf, sizeof(part_buf), _STREAM_PART,
                           fb->len, fb->timestamp.tv_sec, fb->timestamp.tv_usec);

    res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, part_buf, hlen);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);

    esp_camera_fb_return(fb);

    if (res != ESP_OK) break;
  }

  return ESP_FAIL;
}

// Shared handler for all camera setting endpoints.
// user_ctx holds the setting name string.
static esp_err_t setting_handler(httpd_req_t *req) {
  const char *name = (const char *)req->user_ctx;
  char query[32], val_str[8];

  if (httpd_req_get_url_query_str(req, query, sizeof(query)) != ESP_OK ||
      httpd_query_key_value(query, "val", val_str, sizeof(val_str)) != ESP_OK) {
    httpd_resp_send_404(req);
    return ESP_FAIL;
  }

  int val = atoi(val_str);
  sensor_t *s = esp_camera_sensor_get();
  int res = -1;

  if      (!strcmp(name, "resolution")) res = s->set_framesize(s, (framesize_t)val);
  else if (!strcmp(name, "quality"))    res = s->set_quality(s, val);
  else if (!strcmp(name, "brightness")) res = s->set_brightness(s, val);
  else if (!strcmp(name, "contrast"))   res = s->set_contrast(s, val);
  else if (!strcmp(name, "saturation")) res = s->set_saturation(s, val);

  if (res != 0) return httpd_resp_send_500(req);

  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, NULL, 0);
}

void startCameraServer() {
  static const char *names[] = {"resolution", "quality", "brightness", "contrast", "saturation"};
  static const char *uris[]  = {"/resolution", "/quality", "/brightness", "/contrast", "/saturation"};

  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.max_uri_handlers = 8;

  if (httpd_start(&camera_httpd, &config) == ESP_OK) {
    for (int i = 0; i < 5; i++) {
      httpd_uri_t uri = {};
      uri.uri      = uris[i];
      uri.method   = HTTP_GET;
      uri.handler  = setting_handler;
      uri.user_ctx = (void *)names[i];
      httpd_register_uri_handler(camera_httpd, &uri);
    }
    log_i("Camera server on port %u", config.server_port);
  }

  config.server_port += 1;
  config.ctrl_port   += 1;

  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_uri_t stream_uri = {};
    stream_uri.uri     = "/stream";
    stream_uri.method  = HTTP_GET;
    stream_uri.handler = stream_handler;
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    log_i("Stream server on port %u", config.server_port);
  }
}
