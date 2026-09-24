#include <Arduino.h>

// ============================================================
// DRV8871 CONTROL PINS
// ============================================================

const int rotatorMotorPin1 = 32;   // DRV8871 IN1
const int rotatorMotorPin2 = 33;   // DRV8871 IN2


// ============================================================
// RPM CONTROL RANGE
// ============================================================

const float RPM_MIN = 500.0;
const float RPM_MAX = 800.0;


// ============================================================
// CALIBRATION CURVE
//
// RPM = 46.071 * PWM - 6299
//
// Therefore:
//
// PWM = (RPM + 6299) / 46.071
// ============================================================

const float CAL_SLOPE = 46.071;
const float CAL_INTERCEPT = 6299.0;


// ============================================================
// PWM CONFIGURATION
// ============================================================

const int PWM_MIN = 0;
const int PWM_MAX = 255;

const int PWM_FREQ = 20000;       // 20 kHz
const int PWM_RESOLUTION = 8;     // 8-bit = 0-255


// ============================================================
// CONVERT RPM TO PWM
// ============================================================

int rpmToPWM(float rpm) {

  float pwm = (rpm + CAL_INTERCEPT) / CAL_SLOPE;

  return round(pwm);
}


// ============================================================
// STOP MOTOR
// ============================================================

void stopMotor() {

  analogWrite(rotatorMotorPin1, 0);
  analogWrite(rotatorMotorPin2, 0);

  Serial.println("ACK STOP");
}


// ============================================================
// ROTATE CLOCKWISE
// ============================================================

void rotateClockwise(float rpm) {

  // Check RPM range
  if (rpm < RPM_MIN || rpm > RPM_MAX) {

    Serial.print("ERR RPM must be between ");
    Serial.print(RPM_MIN);
    Serial.print(" and ");
    Serial.println(RPM_MAX);

    return;
  }

  // Convert RPM to PWM
  int pwm = rpmToPWM(rpm);

  // Safety limit
  pwm = constrain(pwm, PWM_MIN, PWM_MAX);

  // DRV8871:
  // IN1 = PWM
  // IN2 = LOW

  analogWrite(rotatorMotorPin2, 0);
  analogWrite(rotatorMotorPin1, pwm);

  // Report command
  Serial.print("ACK CLOCK | RPM=");
  Serial.print(rpm);
  Serial.print(" | PWM=");
  Serial.println(pwm);
}


// ============================================================
// ROTATE COUNTERCLOCKWISE
// ============================================================

void rotateUClockwise(float rpm) {

  // Check RPM range
  if (rpm < RPM_MIN || rpm > RPM_MAX) {

    Serial.print("ERR RPM must be between ");
    Serial.print(RPM_MIN);
    Serial.print(" and ");
    Serial.println(RPM_MAX);

    return;
  }

  // Convert RPM to PWM
  int pwm = rpmToPWM(rpm);

  // Safety limit
  pwm = constrain(pwm, PWM_MIN, PWM_MAX);

  // DRV8871:
  // IN1 = LOW
  // IN2 = PWM

  analogWrite(rotatorMotorPin1, 0);
  analogWrite(rotatorMotorPin2, pwm);

  // Report command
  Serial.print("ACK UCLOCK | RPM=");
  Serial.print(rpm);
  Serial.print(" | PWM=");
  Serial.println(pwm);
}


// ============================================================
// PROCESS SERIAL COMMAND
// ============================================================

void processCommand(const String &rawCommand) {

  String command = rawCommand;

  command.trim();

  if (command.length() == 0) {
    return;
  }

  // Make a copy in uppercase for command comparison
  String commandUpper = command;
  commandUpper.toUpperCase();


  // ----------------------------------------------------------
  // STOP
  // ----------------------------------------------------------

  if (commandUpper == "STOP") {

    stopMotor();

    return;
  }


  // ----------------------------------------------------------
  // CLOCK
  //
  // Example:
  // clock 500
  // clock 750
  // clock 800
  // ----------------------------------------------------------

  if (commandUpper.startsWith("CLOCK ")) {

    String rpmText = command.substring(6);

    rpmText.trim();

    if (rpmText.length() == 0) {

      Serial.println("ERR Use: clock <500-800>");

      return;
    }

    float rpm = rpmText.toFloat();

    rotateClockwise(rpm);

    return;
  }


  // ----------------------------------------------------------
  // UCLOCK
  //
  // Example:
  // uclock 500
  // uclock 750
  // uclock 800
  // ----------------------------------------------------------

  if (commandUpper.startsWith("UCLOCK ")) {

    String rpmText = command.substring(7);

    rpmText.trim();

    if (rpmText.length() == 0) {

      Serial.println("ERR Use: uclock <500-800>");

      return;
    }

    float rpm = rpmText.toFloat();

    rotateUClockwise(rpm);

    return;
  }


  // ----------------------------------------------------------
  // UNKNOWN COMMAND
  // ----------------------------------------------------------

  Serial.println("ERR Unknown command");
}


// ============================================================
// SETUP
// ============================================================

void setup() {

  Serial.begin(115200);

  // Configure motor pins
  pinMode(rotatorMotorPin1, OUTPUT);
  pinMode(rotatorMotorPin2, OUTPUT);


  // Configure PWM frequency
  analogWriteFrequency(rotatorMotorPin1, PWM_FREQ);
  analogWriteFrequency(rotatorMotorPin2, PWM_FREQ);

  // Configure PWM resolution
  analogWriteResolution(rotatorMotorPin1, PWM_RESOLUTION);
  analogWriteResolution(rotatorMotorPin2, PWM_RESOLUTION);


  // Make sure motor starts stopped
  analogWrite(rotatorMotorPin1, 0);
  analogWrite(rotatorMotorPin2, 0);


  // ----------------------------------------------------------
  // SERIAL INFORMATION
  // ----------------------------------------------------------

  Serial.println();
  Serial.println("=================================");
  Serial.println("DRV8871 ROTATOR CONTROLLER");
  Serial.println("=================================");

  Serial.println("Calibration:");
  Serial.println("RPM = 46.071 * PWM - 6299");

  Serial.println();
  Serial.println("RPM range: 500 - 800");
  Serial.println("PWM frequency: 20 kHz");

  Serial.println();
  Serial.println("Commands:");
  Serial.println("  clock 500");
  Serial.println("  clock 600");
  Serial.println("  clock 700");
  Serial.println("  clock 800");

  Serial.println("  uclock 500");
  Serial.println("  uclock 600");
  Serial.println("  uclock 700");
  Serial.println("  uclock 800");

  Serial.println("  stop");

  Serial.println();
  Serial.println("Ready.");
}


// ============================================================
// MAIN LOOP
// ============================================================

void loop() {

  if (Serial.available() > 0) {

    String command = Serial.readStringUntil('\n');

    processCommand(command);
  }
}