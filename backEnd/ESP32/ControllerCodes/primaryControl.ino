#include <Arduino.h>

// added accelerator library for smooth acceleration/deceleration
#include <AccelStepper.h>

//pins for rotation control 
const int rotatorMotorPin1 = 32;   // DRV8871 IN1
const int rotatorMotorPin2 = 33;   // DRV8871 IN2

//RPM CONTROL RANGE
const float RPM_MIN = 500.0;
const float RPM_MAX = 800.0;

// ============================================================
// CALIBRATION CURVE
// RPM = 46.071 * PWM - 6299
// Therefore:
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

//Pins for endRace sensor
const int Z_endRacePin = 17;
const int X_endRacePin = 16;
//Variables to track the state in console
bool zLastEndstopState = false;
bool xLastEndstopState = false;
bool zEndstopCandidate = false;
bool xEndstopCandidate = false;
unsigned long zEndstopChangeStart = 0;
unsigned long xEndstopChangeStart = 0;
const int ENDSTOP_CONFIRM_READS = 5;  // number of reads to confirm if the platform is in home
const unsigned long ENDSTOP_DEBOUNCE_MS = 50;

//Pins for step motor control axis Z
const int Z_stepPin = 18;
const int Z_dirPin = 5;
const int Z_enablePin = 27;
const int Z_maxStepHome = 100000;

//Pins for step motor control axis X
const int X_stepPin = 25;
const int X_dirPin = 26;
const int X_enablePin = 14;
const int X_maxStepHome = 5000;

//maximum speed in steps/second
const int Z_maxSpeed = 2000;
const int X_maxSpeed = 500;

//Accelaration in steps/second^2
const float Z_acceleration = 800.0;
const float X_acceleration = 200.0;

//Vial position assignament variable
String currentLocation = "UNKNOWN";

//AccelStepper Driver mode
AccelStepper Zmotor(AccelStepper::DRIVER, Z_stepPin, Z_dirPin);
AccelStepper Xmotor(AccelStepper::DRIVER, X_stepPin, X_dirPin);

void setup (){
    Serial.begin (115200);
    delay(500);

    //End Race Sensor Mode
    pinMode(Z_endRacePin, INPUT_PULLDOWN);
    pinMode(X_endRacePin, INPUT_PULLDOWN);
    
    // Step motor pins Mode
    pinMode(Z_stepPin, OUTPUT);
    pinMode(Z_dirPin, OUTPUT);
    pinMode(Z_enablePin, OUTPUT);

    pinMode(X_stepPin, OUTPUT);
    pinMode(X_dirPin, OUTPUT);
    pinMode(X_enablePin, OUTPUT);

    //Initial conditions for motors
    //For motor Z
    digitalWrite(Z_stepPin, LOW);
    digitalWrite(Z_dirPin, LOW);
    digitalWrite(Z_enablePin, HIGH);
    //Max speed and accelaration
    Zmotor.setMaxSpeed(Z_maxSpeed);
    Zmotor.setAcceleration(Z_acceleration);

    //For motor X
    digitalWrite(X_stepPin, LOW);
    digitalWrite(X_dirPin, LOW);
    digitalWrite(X_enablePin, HIGH);
    //Max speed and accelaration
    Xmotor.setMaxSpeed(X_maxSpeed);
    Xmotor.setAcceleration(X_acceleration);

    //Initial endstop states
    zLastEndstopState = zEndStopActive();
    xLastEndstopState = xEndStopActive();
    zEndstopCandidate = zLastEndstopState;
    xEndstopCandidate = xLastEndstopState;

    //Serial information
    Serial.println("ESP32 stepper controller ready");
    Serial.println("Use: MOVE_UP 20 / MOVE_DOWN 20 / MOVE_RIGHT 100 / MOVE_LEFT 100");
    Serial.println("Use: HOME_POSITION (Z down, then X left)");
    Serial.println("Z endstop: GPIO17, X endstop: GPIO16 (HIGH = triggered)");
}

//=============================================================
//FUNCTIONS FOR ROTATOR MOTOR
//=============================================================
int rpmToPWM(float rpm) {
  float pwm = (rpm + CAL_INTERCEPT) / CAL_SLOPE;
  return round(pwm);
}

void stopRotator(){
    analogWrite(rotatorMotorPin1, 0);
    analogWrite(rotatorMotorPin2, 0);
    Serial.println("ACK STOP ROTATOR");
}

void rotateClockwise(float rpm) {
    if (rpm < RPM_MIN || rpm > RPM_MAX) {
        Serial.print("ERR RPM must be between ");
        Serial.print(RPM_MIN);
        Serial.print(" and ");
        Serial.println(RPM_MAX);
        return;
    }

    //convert RPM to PWM
    int pwm = rpmToPWM(rpm);

    //Safety limit
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

void rotateCounterClockwise(float rpm) {
    if (rpm < RPM_MIN || rpm > RPM_MAX) {
        Serial.print("ERR RPM must be between ");
        Serial.print(RPM_MIN);
        Serial.print(" and ");
        Serial.println(RPM_MAX);
        return;
    }

    //convert RPM to PWM
    int pwm = rpmToPWM(rpm);

    //Safety limit
    pwm = constrain(pwm, PWM_MIN, PWM_MAX);
    
    // DRV8871:
    // IN1 = LOW
    // IN2 = PWM
    analogWrite(rotatorMotorPin1, 0);
    analogWrite(rotatorMotorPin2, pwm);
      // Report command
    Serial.print("ACK COUNTERCLOCK | RPM=");
    Serial.print(rpm);
    Serial.print(" | PWM=");
    Serial.println(pwm);
}

//=============================================================
//FUNCTIONS FOR ENDSTOP SENSORS
//=============================================================
bool zEndStopActive() {
    return digitalRead(Z_endRacePin) == HIGH;
}

bool xEndStopActive() {
    return digitalRead(X_endRacePin) == HIGH;
}

void updateEndstopStates() {
  unsigned long now = millis();

  bool zReading = zEndStopActive();
  if (zReading != zEndstopCandidate) {
    zEndstopCandidate = zReading;
    zEndstopChangeStart = now;
  }
  if (zEndstopCandidate != zLastEndstopState && (now - zEndstopChangeStart) >= ENDSTOP_DEBOUNCE_MS) {
    zLastEndstopState = zEndstopCandidate;
    Serial.print("Z endstop: ");
    Serial.println(zLastEndstopState ? "ACTIVE" : "DEACTIVATED");
  }

  bool xReading = xEndStopActive();
  if (xReading != xEndstopCandidate) {
    xEndstopCandidate = xReading;
    xEndstopChangeStart = now;
  }
  if (xEndstopCandidate != xLastEndstopState && (now - xEndstopChangeStart) >= ENDSTOP_DEBOUNCE_MS) {
    xLastEndstopState = xEndstopCandidate;
    Serial.print("X endstop: ");
    Serial.println(xLastEndstopState ? "ACTIVE" : "DEACTIVATED");
  }
}

// Logic to see if the home sensor is active
bool endstopConfirmed(int endstopPin) {
  for (int i = 0; i < ENDSTOP_CONFIRM_READS; ++i) {
    if (digitalRead(endstopPin) != HIGH) {
      return false;
    }
    delayMicroseconds(200);
  }
  return true;
}
   

void homePosition(AccelStepper &motor, int endstopPin, int enablePin, int maxSteps) {

    // first Z home position
    //check z home sensor
    bool AlreadyHome = endstopConfirmed(endstopPin);
    
    //Execute motion
    if (AlreadyHome) {
        Serial.println("Motor already at home position");
        motor.setCurrentPosition(0);
        Serial.println("Home position = 0");
        Serial.println("Checking other platform...");
        return;
    } 

    //Start Homing
    Serial.println("Homing motor...");
    digitalWrite(enablePin, LOW);
    motor.moveTo(-maxSteps);

    while (motor.distanceToGo() != 0) {
        if (endstopConfirmed(endstopPin)) {
            Serial.println("Motor reached home position");
            motor.setCurrentPosition(0);
            digitalWrite(enablePin, HIGH);
            return;
    
        }
        motor.run();
    }
            
     Serial.println("ERR HOME NOT FOUND");
    digitalWrite(enablePin, HIGH);
               
}
        

void moveStepper(AccelStepper &motor, int dirPin, int enablePin, long steps, bool direction) {

    // Check that the requested number of steps is valid
    if (steps <= 0) {
        Serial.println("ERR INVALID_STEP_COUNT");
        return;
    }

    // Set actual DIR pin before moving. This is the part that changes rotation direction.
    digitalWrite(dirPin, direction ? HIGH : LOW);

    // Enable motor
    digitalWrite(enablePin, LOW);

    // assign direction using the sign of the target position
    motor.move(direction ? steps : -steps);

    // execute movement
    while (motor.distanceToGo() != 0) {
        motor.run();
    }

    digitalWrite(enablePin, HIGH);
    Serial.println("MOVE_COMPLETE");
}

long parseSteps(const String &command) {
    int lastSpace = command.lastIndexOf(' ');
    if (lastSpace < 0) {
        return 0;
    }

    String stepText = command.substring(lastSpace + 1);
    stepText.trim();

    if (stepText.length() == 0) {
        return 0;
    }
    return stepText.toInt();
}

void homeToVial(int vialNumber) {
     
    Serial.print("Homing... ");
    Serial.println(vialNumber);

    // Move to home position first
    homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
    homePosition(Xmotor, X_endRacePin, X_enablePin, X_maxStepHome);

    // Move to the specified vial position
    switch (vialNumber) {
        case 1:
            moveStepper(Xmotor, X_dirPin, X_enablePin, 1060, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            break;
        case 2:
            moveStepper(Xmotor, X_dirPin, X_enablePin, 795, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            break;
        case 3:
            moveStepper(Xmotor, X_dirPin, X_enablePin, 535, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            break;
        case 4:
            moveStepper(Xmotor, X_dirPin, X_enablePin, 285, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            break;
        case 5:
            moveStepper(Xmotor, X_dirPin, X_enablePin, 20, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            break;
        default:
            Serial.println("ERR INVALID_VIAL_NUMBER");
            return;
    }

    Serial.print("Device is now in vial ");
    Serial.println(vialNumber);
}

void serialComm (const String &command) {
    String cmd = command;
    cmd.trim();
    cmd.toUpperCase();

    // ROTATOR MOTOR COMMANDS
    if (cmd == "STOP_ROTATOR") {
        stopRotator();
    }

    if (cmd.startsWith("ROTATE_CLOCK ")) {
        Serial.println("ACK");
        String rpmText = cmd.substring(13);
        rpmText.trim();

        if (rpmText.length() == 0){
            Serial.println("ERR Use: clock <500-800>");
            return;
        }
        float rpm = rpmText.toFloat();
        rotateClockwise(rpm);
    }

    if (cmd.startsWith("ROTATE_UCLOCK ")) {
        Serial.println("ACK");
        String rpmText = cmd.substring(14);
        rpmText.trim();

        if (rpmText.length() == 0){
            Serial.println("ERR Use: uclock <500-800>");
            return;
        }
        float rpm = rpmText.toFloat();
        rotateUnclockwise(rpm);
    }
    
    // .............
    //Manual operation
    // .................
    if (cmd.startsWith("MOVE_UP")) {
        Serial.println("ACK");
        moveStepper(Zmotor, Z_dirPin, Z_enablePin, parseSteps(cmd), true);
        currentLocation = "UNKNOWN";
    }

    if (cmd.startsWith("MOVE_DOWN")) {
        Serial.println("ACK");
        moveStepper(Zmotor, Z_dirPin, Z_enablePin, parseSteps(cmd), false);
        currentLocation = "UNKNOWN";
    }

    if (cmd.startsWith("MOVE_RIGHT")) {
        Serial.println("ACK");
        moveStepper(Xmotor, X_dirPin, X_enablePin, parseSteps(cmd), true);
        currentLocation = "UNKNOWN";
    }

    if (cmd.startsWith("MOVE_LEFT")) {
        Serial.println("ACK");
        moveStepper(Xmotor, X_dirPin, X_enablePin, parseSteps(cmd), false);
        currentLocation = "UNKNOWN";
    }


    //..............
    //HOMING COMMANDS
    // ..............
    if (cmd == "HOME_POSITION" || cmd == "HOME") {
        Serial.println("ACK");
        homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
        homePosition(Xmotor, X_endRacePin, X_enablePin, X_maxStepHome);
        Serial.println("DONE");
        currentLocation = "HOME";
    }

    if (cmd == "HOME_POSITION_Z" || cmd == "HOME_Z") {
        Serial.println("ACK");
        homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
        Serial.println("DONE");
        if (currentLocation == "VIAL1" || currentLocation == "VIAL2" || currentLocation == "VIAL3" || currentLocation == "VIAL4" || currentLocation == "VIAL5") {
            return;
        }
        currentLocation = "UNKNOWN";
    }

    if (cmd == "HOME_POSITION_X" || cmd == "HOME_X") {
        Serial.println("ACK");
        homePosition(Xmotor, X_endRacePin, X_enablePin, X_maxStepHome);
        Serial.println("DONE");
        currentLocation = "UNKNOWN";
    }

    //..............
    //HOME TO VIAL COMMANDS
    // ..............
    if (cmd == "HOME_TO_VIAL1") {
        Serial.println("ACK");
        if (currentLocation == "VIAL1") {
            Serial.println("Already at VIAL1, no movement");
            return;
        }
        homeToVial(1);
        currentLocation = "VIAL1";
    }

    if (cmd == "HOME_TO_VIAL2") {
        Serial.println("ACK");
        if (currentLocation == "VIAL2") {
            Serial.println("Already at VIAL2, no movement");
            return;
        }
        homeToVial(2);
        currentLocation = "VIAL2";
    }

    if (cmd == "HOME_TO_VIAL3") {
        Serial.println("ACK");
        if (currentLocation == "VIAL3") {
            Serial.println("Already at VIAL3, no movement");
            return;
        }
        homeToVial(3);
        currentLocation = "VIAL3";
    }

    if (cmd == "HOME_TO_VIAL4") {
        Serial.println("ACK");
        if (currentLocation == "VIAL4") {
            Serial.println("Already at VIAL4, no movement");
            return;
        }
        homeToVial(4);
        currentLocation = "VIAL4";
    }

    if (cmd == "HOME_TO_VIAL5") {
        Serial.println("ACK");
        if (currentLocation == "VIAL5") {
            Serial.println("Already at VIAL5, no movement");
            return;
        }
        homeToVial(5);
        currentLocation = "VIAL5";
    }

    //..............
    //VIAL1 TO VIAL2,3,4,5 COMMANDS
    // ..............
    if (cmd == "VIAL1_TO_VIAL2") {
        Serial.println("ACK");
        if (currentLocation == "VIAL1") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL2";
            Serial.println("DONE");
        } else {
            homeToVial(1);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL2";
        }
    }

    if (cmd == "VIAL1_TO_VIAL3") {
        Serial.println("ACK");
        if (currentLocation == "VIAL1") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL3";
            Serial.println("DONE");
        } else {
            homeToVial(1);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL3";
        }
    }

    if (cmd == "VIAL1_TO_VIAL4") {
        Serial.println("ACK");
        if (currentLocation == "VIAL1") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 795, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL4";
            Serial.println("DONE");
        } else {
            homeToVial(1);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 795, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL4";
        }
    }

    if (cmd == "VIAL1_TO_VIAL5") {
        Serial.println("ACK");
        if (currentLocation == "VIAL1") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 1060, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL5";
            Serial.println("DONE");
        } else {
            homeToVial(1);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 1060, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL5";
        }
    }

    //..............
    //VIAL2 TO VIAL1,3,4,5 COMMANDS
    // ..............
    if (cmd == "VIAL2_TO_VIAL1") {
        Serial.println("ACK");
        if (currentLocation == "VIAL2") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL1";
            Serial.println("DONE");
        } else {
            homeToVial(2);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL1";
        }
    }

    if (cmd == "VIAL2_TO_VIAL3") {
        Serial.println("ACK");
        if (currentLocation == "VIAL2") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL3";
            Serial.println("DONE");
        } else {
            homeToVial(2);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL3";
        }
    }

    if (cmd == "VIAL2_TO_VIAL4") {
        Serial.println("ACK");
        if (currentLocation == "VIAL2") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL4";
            Serial.println("DONE");
        } else {
            homeToVial(2);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL4";
        }
    }

    if (cmd == "VIAL2_TO_VIAL5") {
        Serial.println("ACK");
        if (currentLocation == "VIAL2") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 795, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL5";
            Serial.println("DONE");
        } else {
            homeToVial(2);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 795, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL5";
        }
    }

    //..............
    //VIAL3 TO VIAL1,2,4,5 COMMANDS
    // ..............
    if (cmd == "VIAL3_TO_VIAL1") {
        Serial.println("ACK");
        if (currentLocation == "VIAL3") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL1";
            Serial.println("DONE");
        } else {
            homeToVial(3);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL1";
        }
    }

    if (cmd == "VIAL3_TO_VIAL2") {
        Serial.println("ACK");
        if (currentLocation == "VIAL3") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL2";
            Serial.println("DONE");
        } else {
            homeToVial(3);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL2";
        }
    }

    if (cmd == "VIAL3_TO_VIAL4") {
        Serial.println("ACK");
        if (currentLocation == "VIAL3") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL4";
            Serial.println("DONE");
        } else {
            homeToVial(3);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL4";
        }
    }

    if (cmd == "VIAL3_TO_VIAL5") {
        Serial.println("ACK");
        if (currentLocation == "VIAL3") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL5";
            Serial.println("DONE");
        } else {
            homeToVial(3);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL5";
        }
    }

    //..............
    //VIAL4 TO VIAL1,2,3,5 COMMANDS
    // ..............
    if (cmd == "VIAL4_TO_VIAL1") {
        Serial.println("ACK");
        if (currentLocation == "VIAL4") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 795, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL1";
            Serial.println("DONE");
        } else {
            homeToVial(4);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 795, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL1";
        }
    }

    if (cmd == "VIAL4_TO_VIAL2") {
        Serial.println("ACK");
        if (currentLocation == "VIAL4") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL2";
            Serial.println("DONE");
        } else {
            homeToVial(4);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL2";
        }
    }

    if (cmd == "VIAL4_TO_VIAL3") {
        Serial.println("ACK");
        if (currentLocation == "VIAL4") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL3";
            Serial.println("DONE");
        } else {
            homeToVial(4);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL3";
        }
    }

    if (cmd == "VIAL4_TO_VIAL5") {
        Serial.println("ACK");
        if (currentLocation == "VIAL4") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL5";
            Serial.println("DONE");
        } else {
            homeToVial(4);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, false);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL5";
        }
    }

    //..............
    //VIAL5 TO VIAL1,2,3,4 COMMANDS
    // ..............
    if (cmd == "VIAL5_TO_VIAL1") {
        Serial.println("ACK");
        if (currentLocation == "VIAL5") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 1060, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL1";
            Serial.println("DONE");
        } else {
            homeToVial(5);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 1060, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL1";
        }
    }

    if (cmd == "VIAL5_TO_VIAL2") {
        Serial.println("ACK");
        if (currentLocation == "VIAL5") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 795, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL2";
            Serial.println("DONE");
        } else {
            homeToVial(5);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 795, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL2";
        }
    }

    if (cmd == "VIAL5_TO_VIAL3") {
        Serial.println("ACK");
        if (currentLocation == "VIAL5") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL3";
            Serial.println("DONE");
        } else {
            homeToVial(5);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 530, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL3";
        }
    }

    if (cmd == "VIAL5_TO_VIAL4") {
        Serial.println("ACK");
        if (currentLocation == "VIAL5") {
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL4";
            Serial.println("DONE");
        } else {
            homeToVial(5);
            homePosition(Zmotor, Z_endRacePin, Z_enablePin, Z_maxStepHome);
            moveStepper(Xmotor, X_dirPin, X_enablePin, 265, true);
            moveStepper(Zmotor, Z_dirPin, Z_enablePin, 42000, true);
            currentLocation = "VIAL4";
        }
    }
   
}

void loop (){
    if (Serial.available()) {
        String command = Serial.readStringUntil('\n');
        if (command.length() > 0) {
            serialComm(command);
        }
    }

    //Report Endstop activations/deactivations while idle.
    updateEndstopStates();
}




