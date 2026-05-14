#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>

#include <MQTTAsync.h>

namespace {
constexpr int kQos = 1;

std::string getEnvOrDefault(const char *name, const char *fallback) {
  const char *value = std::getenv(name);
  if (value == nullptr || *value == '\0') {
    return fallback;
  }
  return value;
}

double getEnvDouble(const char *name, double fallback) {
  const char *value = std::getenv(name);
  if (value == nullptr || *value == '\0') {
    return fallback;
  }
  char *endPtr = nullptr;
  const double parsed = std::strtod(value, &endPtr);
  if (endPtr == value) {
    return fallback;
  }
  return parsed;
}
} // namespace

int main() {
  const std::string host = getEnvOrDefault("MQTT_HOST", "mosquitto");
  const std::string port = getEnvOrDefault("MQTT_PORT", "1883");
  const std::string topic = getEnvOrDefault("MQTT_TOPIC", "controller/sim/sine");
  const double amplitude = getEnvDouble("SINE_AMPLITUDE", 10.0);
  const double frequencyHz = getEnvDouble("SINE_FREQUENCY_HZ", 0.1);
  const double stepSeconds = getEnvDouble("SINE_STEP_SECONDS", 0.5);

  const std::string brokerUri = "tcp://" + host + ":" + port;
  const std::string clientId = "forte-sine-cpp";

  MQTTAsync client = nullptr;
  if (MQTTAsync_create(&client, brokerUri.c_str(), clientId.c_str(), MQTTCLIENT_PERSISTENCE_NONE, nullptr) != MQTTASYNC_SUCCESS) {
    std::cerr << "Failed to create MQTT client" << std::endl;
    return 1;
  }

  MQTTAsync_connectOptions connectOptions = MQTTAsync_connectOptions_initializer;
  connectOptions.cleansession = 1;
  connectOptions.automaticReconnect = 1;
  connectOptions.minRetryInterval = 1;
  connectOptions.maxRetryInterval = 30;

  std::cout << "Connecting to MQTT broker at " << brokerUri << std::endl;
  if (MQTTAsync_connect(client, &connectOptions) != MQTTASYNC_SUCCESS) {
    std::cerr << "Failed to start MQTT connection" << std::endl;
    MQTTAsync_destroy(&client);
    return 1;
  }

  std::this_thread::sleep_for(std::chrono::seconds(2));
  std::cout << "Publishing sine wave to topic " << topic << std::endl;

  double t = 0.0;
  while (true) {
    const double value = amplitude * std::sin(2.0 * M_PI * frequencyHz * t);

    std::ostringstream payload;
    payload << std::fixed << std::setprecision(6) << value;
    const std::string text = payload.str();

    MQTTAsync_message message = MQTTAsync_message_initializer;
    message.payload = const_cast<char *>(text.c_str());
    message.payloadlen = static_cast<int>(text.size());
    message.qos = kQos;
    message.retained = 0;

    MQTTAsync_responseOptions responseOptions = MQTTAsync_responseOptions_initializer;
    const int publishRc = MQTTAsync_sendMessage(client, topic.c_str(), &message, &responseOptions);
    if (publishRc != MQTTASYNC_SUCCESS) {
      std::cerr << "Publish failed with code " << publishRc << std::endl;
    }

    std::cout << "Published " << text << std::endl;
    std::this_thread::sleep_for(std::chrono::duration<double>(stepSeconds));
    t += stepSeconds;
  }
}
