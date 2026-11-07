// シリアルで受けた 1 文字でリレーを入り切りする最小のスケッチ。
// Jetson 側の conveyor-mcp（server.py / relay_onoff.py）から操作する。
// シリアルで '1' → リレーON（ベルト回転）、'0' → リレーOFF（停止）
// D7、D8、D6 のリレーを同じタイミングで入り切りする。応答（ON / OFF）は 1 行だけ返す
const int RELAY = 7;   // ベースシールドの D7 ポート
const int RELAY2 = 8;  // ベースシールドの D8 ポート
const int RELAY3 = 6;  // ベースシールドの D6 ポート（3 つめのコンベア）

void setup() {
  pinMode(RELAY, OUTPUT);
  pinMode(RELAY2, OUTPUT);
  pinMode(RELAY3, OUTPUT);
  digitalWrite(RELAY, LOW);
  digitalWrite(RELAY2, LOW);
  digitalWrite(RELAY3, LOW);
  Serial.begin(115200);
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == '1') { digitalWrite(RELAY, HIGH); digitalWrite(RELAY2, HIGH); digitalWrite(RELAY3, HIGH); Serial.println("ON"); }
    if (c == '0') { digitalWrite(RELAY, LOW);  digitalWrite(RELAY2, LOW);  digitalWrite(RELAY3, LOW);  Serial.println("OFF"); }
  }
}
