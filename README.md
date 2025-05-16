# Python Touch Input System

A lightweight Python library offering on-screen touch controls and gesture recognition, with optional mouse fallback.  
Ideal for building touch-driven UIs or games in engines/frameworks like Pygame, Kivy, Ursina, etc.

---

## Features

- **TouchButton**: Simple press/release button with callback support  
- **VirtualJoystick**: Normalized 2D directional input with dead zone and max displacement  
- **GestureRecognizer**: Tap, double-tap, long-press, pinch (and extendable to swipes, rotate, etc.)  
- **Mouse Fallback**: Treat mouse events as touch for platforms without touch support  
- **Extensible**: Hook into any Python graphics/event loop  

---

## Installation

Just clone the repo (no pip package yet):

```bash
git clone https://github.com/<your-username>/python-touch-input-system.git
cd python-touch-input-system
````

Copy `touch_input_system.py` into your project, or install via a future `setup.py`.

---

## Usage

```python
from touch_input_system import TouchButton, VirtualJoystick, GestureRecognizer, TouchInputSystem, TouchPoint, Vec2
import time

def on_button_click(btn_id):
    print(f"Button {btn_id} clicked")

def on_joy_move(vec):
    print(f"Joystick → x:{vec.x:.2f}, y:{vec.y:.2f}")

def on_gesture(name, details):
    print("Gesture:", name, details)

# Initialize components
btn = TouchButton("fire", on_button_click)
joy = VirtualJoystick(on_joy_move, max_displacement=75)
gest = GestureRecognizer(on_gesture)

# Build input system
input_sys = TouchInputSystem()
input_sys.add_button(btn)
input_sys.set_joystick(joy)
input_sys.set_gesture_recognizer(gest)

# (Then feed actual touch/mouse events from your framework into input_sys)
```

---

## API Reference

### `class Vec2(x: float, y: float)`

Simple 2D vector with `.magnitude()` and `.normalized()`.

### `class TouchButton(button_id: str, on_click_callback: Callable)`

* `.handle_press(point: TouchPoint)`
* `.handle_release(point: TouchPoint)`

### `class VirtualJoystick(on_move_callback: Callable, dead_zone_radius=0.1, max_displacement=50.0)`

* `.start_drag(TouchPoint, Vec2 base_center_pos)`
* `.drag(TouchPoint)`
* `.end_drag()`

### `class GestureRecognizer(on_gesture_callback: Callable)`

Recognizes:

* `Tap`, `Double Tap`, `Triple Tap`
* `Two-Finger Tap`, `Three-Finger Tap`
* `Long Press`
* `Pinch` (scale factor)
  *(Swipe & Rotate are placeholders for you to extend.)*

### `class TouchInputSystem()`

* `.add_button(TouchButton)`
* `.set_joystick(VirtualJoystick)`
* `.set_gesture_recognizer(GestureRecognizer)`
* `.on_mouse_button_down(x, y, button_name)` / `.on_mouse_button_up(...)` / `.on_mouse_move(...)`

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Submit a PR with tests/examples

---

## License

[MIT](LICENSE) © Shivam

```

Feel free to adjust names, add badges (build, coverage), or split classes into multiple files as your project grows.
```
