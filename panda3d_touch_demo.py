# This script will set up a basic Panda3D application and include:

# A clickable Touch Button.
# A draggable Virtual Joystick.
# A Gesture Area that recognizes taps, double-taps, long presses, and simulates pinch/swipe feedback.
# Mouse input will be used to simulate single-touch interactions.

from direct.showbase.ShowBase import ShowBase
from direct.gui.DirectGui import DirectButton, DirectFrame, OnscreenText
from panda3d.core import TextNode, CardMaker, NodePath, Vec3, Point3, LineSegs
from panda3d.core import MouseButton
from direct.task import Task
import time
import math

# --- Helper Classes (similar to previous conceptual version) ---
class Vec2:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)

    def __repr__(self):
        return f"Vec2({self.x:.2f}, {self.y:.2f})"

    def magnitude(self):
        return (self.x**2 + self.y**2)**0.5

    def normalized(self):
        mag = self.magnitude()
        if mag == 0:
            return Vec2(0, 0)
        return Vec2(self.x / mag, self.y / mag)

class TouchPoint:
    def __init__(self, id, x, y):
        self.id = id
        self.x = float(x) # Screen coordinates (e.g., aspect2d)
        self.y = float(y)

    def __repr__(self):
        return f"TouchPoint(id={self.id}, x={self.x:.2f}, y={self.y:.2f})"

# --- Core Logic Components ---

class TouchButtonLogic:
    def __init__(self, button_id, on_click_callback):
        self.id = button_id
        self.on_click_callback = on_click_callback
        self.is_pressed = False

    def handle_press(self, point: TouchPoint):
        self.is_pressed = True
        # print(f"ButtonLogic '{self.id}' pressed at ({point.x}, {point.y})")

    def handle_release(self, point: TouchPoint):
        if self.is_pressed:
            self.is_pressed = False
            # print(f"ButtonLogic '{self.id}' released.")
            if self.on_click_callback:
                self.on_click_callback(self.id)

class VirtualJoystickLogic:
    def __init__(self, on_move_callback, dead_zone_radius_normalized=0.1, visual_radius_units=0.15):
        self.on_move_callback = on_move_callback
        self.direction = Vec2(0, 0)
        self.is_dragging = False
        self.base_center_pos_screen = Vec2(0,0) # Center of the joystick base in screen coords (-1 to 1)
        self.max_displacement_units = visual_radius_units # Effective radius for normalization, in screen units
        self.dead_zone_radius_normalized = dead_zone_radius_normalized

    def start_drag(self, touch_point_screen: TouchPoint, joystick_base_center_screen: Vec2):
        self.is_dragging = True
        self.base_center_pos_screen = joystick_base_center_screen
        self._update_direction(touch_point_screen)

    def drag(self, touch_point_screen: TouchPoint):
        if not self.is_dragging:
            return
        self._update_direction(touch_point_screen)

    def end_drag(self):
        if not self.is_dragging:
            return
        self.is_dragging = False
        self.direction = Vec2(0, 0)
        if self.on_move_callback:
            self.on_move_callback(self.direction)
        # print("JoystickLogic drag ended.")

    def _update_direction(self, current_touch_point_screen: TouchPoint):
        dx = current_touch_point_screen.x - self.base_center_pos_screen.x
        dy = current_touch_point_screen.y - self.base_center_pos_screen.y
        
        current_displacement_vec = Vec2(dx, dy)
        distance_from_center_units = current_displacement_vec.magnitude()

        norm_x = dx / self.max_displacement_units if self.max_displacement_units else 0
        norm_y = dy / self.max_displacement_units if self.max_displacement_units else 0
        
        norm_vec = Vec2(norm_x, norm_y)
        norm_distance = norm_vec.magnitude()

        if norm_distance > 1.0:
            norm_vec = norm_vec.normalized()
        
        if norm_distance < self.dead_zone_radius_normalized:
            self.direction = Vec2(0, 0)
        else:
            effective_radius = 1.0 - self.dead_zone_radius_normalized
            if effective_radius <= 0:
                 self.direction = Vec2(0,0)
            else:
                scale = (norm_distance - self.dead_zone_radius_normalized) / effective_radius
                final_vec_normalized = norm_vec.normalized()
                self.direction = Vec2(final_vec_normalized.x * min(1.0, scale), 
                                      final_vec_normalized.y * min(1.0, scale))
        
        if self.on_move_callback:
            self.on_move_callback(self.direction)

class GestureRecognizer:
    MAX_TAP_INTERVAL_SEC = 0.3
    MIN_SWIPE_DISTANCE_UNITS = 0.1 # In screen units (-1 to 1 range)
    LONG_PRESS_DURATION_SEC = 0.7

    def __init__(self, on_gesture_callback, task_mgr):
        self.on_gesture_callback = on_gesture_callback
        self.task_mgr = task_mgr
        
        self.touch_start_time_mono = 0.0
        self.touch_start_points = {} # Key: touch_id (0 for mouse), Value: TouchPoint
        self.last_tap_time_mono = 0.0
        self.tap_count = 0
        self.is_dragging_initiated = False
        
        self._long_press_task_name = "longPressCheckTask"
        self._finalize_tap_task_name = "finalizeTapGestureTask"

    def _emit_gesture(self, name, details=None):
        if self.on_gesture_callback:
            self.on_gesture_callback(name, details)

    def _clear_pending_tasks(self):
        self.task_mgr.remove(self._long_press_task_name)
        self.task_mgr.remove(self._finalize_tap_task_name)

    def _reset_tap_sequence(self):
        self.tap_count = 0
        self.task_mgr.remove(self._finalize_tap_task_name)

    def _long_press_check_task(self, task):
        # This task runs if the finger is held down long enough
        if self.touch_start_points and not self.is_dragging_initiated: # Still pressed, no drag
            # Check if the specific touch that initiated this is still the primary one
            # For single touch (mouse), this is simpler
            if 0 in self.touch_start_points: # Mouse is touch ID 0
                 self._emit_gesture("Long Press")
                 self.touch_start_points.clear() # Consume points
                 self._reset_tap_sequence()
        return Task.done # Task is finished

    def _finalize_tap_gesture_task(self, task):
        # This task runs after MAX_TAP_INTERVAL to finalize tap count
        if self.tap_count > 0: # Ensure there was a tap to finalize
            num_fingers_at_start = task.userData['num_fingers_at_start']
            
            if num_fingers_at_start == 1: # Single finger taps
                if self.tap_count == 1: self._emit_gesture("Tap")
                elif self.tap_count == 2: self._emit_gesture("Double Tap")
                elif self.tap_count >= 3: self._emit_gesture("Triple Tap")
            # elif num_fingers_at_start == 2: self._emit_gesture("Two-Finger Tap") # For multi-touch
            # ... etc.
            
        self._reset_tap_sequence() # Reset for the next sequence
        # Do not clear touch_start_points here, as it might be needed if a drag starts *after* tap sequence
        return Task.done

    def handle_touch_down(self, point: TouchPoint): # Single point for mouse
        self._clear_pending_tasks() # Clear any previous pending tasks
        current_time_mono = time.monotonic()
        self.is_dragging_initiated = False
        
        self.touch_start_points = {point.id: point}
        self.touch_start_time_mono = current_time_mono

        # Schedule long press check
        self.task_mgr.doMethodLater(self.LONG_PRESS_DURATION_SEC, 
                                   self._long_press_check_task, 
                                   self._long_press_task_name)

    def handle_touch_move(self, point: TouchPoint):
        if not self.touch_start_points or point.id not in self.touch_start_points:
            return

        start_point = self.touch_start_points[point.id]
        dx = point.x - start_point.x
        dy = point.y - start_point.y
        distance_sq = dx*dx + dy*dy

        # Check if significant movement occurred
        if distance_sq > (0.01)**2: # Small threshold to consider it a drag
            self.is_dragging_initiated = True
            self.task_mgr.remove(self._long_press_task_name) # Movement cancels long press

        # Update current position of the tracked touch
        self.touch_start_points[point.id] = point 

        # Simplified Pinch/Rotate simulation (would need two points for real)
        if self.is_dragging_initiated:
             # For demo, we can't get true scale/angle from one mouse point.
             # Emit a "Drag Move" to show activity.
             self._emit_gesture("Drag Move", {"dx": round(dx,2), "dy": round(dy,2)})


    def handle_touch_up(self, point: TouchPoint):
        if not self.touch_start_points or point.id not in self.touch_start_points:
            return
        
        self.task_mgr.remove(self._long_press_task_name) # Lifting finger cancels pending long press
        
        current_time_mono = time.monotonic()
        duration_sec = current_time_mono - self.touch_start_time_mono
        start_point = self.touch_start_points[point.id]

        if not self.is_dragging_initiated and duration_sec < self.LONG_PRESS_DURATION_SEC:
            # Potential tap
            if current_time_mono - self.last_tap_time_mono < self.MAX_TAP_INTERVAL_SEC and self.tap_count > 0:
                self.tap_count += 1
            else:
                self._reset_tap_sequence() # Important: Clears pending finalize task if any
                self.tap_count = 1
            self.last_tap_time_mono = current_time_mono
            
            num_fingers_at_start = len(self.touch_start_points) # For mouse, always 1
            # Schedule tap finalization
            self.task_mgr.doMethodLater(self.MAX_TAP_INTERVAL_SEC, 
                                       self._finalize_tap_gesture_task, 
                                       self._finalize_tap_task_name,
                                       userData={'num_fingers_at_start': num_fingers_at_start})

        elif self.is_dragging_initiated: # It was a drag/swipe
            dx = point.x - start_point.x
            dy = point.y - start_point.y
            distance = (dx**2 + dy**2)**0.5

            if distance > self.MIN_SWIPE_DISTANCE_UNITS:
                direction = ""
                if abs(dx) > abs(dy): direction = "Right" if dx > 0 else "Left"
                else: direction = "Down" if dy > 0 else "Up"
                self._emit_gesture(f"Swipe {direction}", {"distance": round(distance,2)})
            else:
                self._emit_gesture("Drag End", {"dx": round(dx,2), "dy": round(dy,2)})
            
            self.touch_start_points.clear()
            self._reset_tap_sequence() # Also clear tap state if it was a drag
        
        # Don't clear touch_start_points immediately for taps, let _finalize_tap_gesture_task handle it or next down
        # If it wasn't a drag and not a tap (e.g. long press emitted, or duration too long for tap)
        # then touch_start_points might have been cleared by long_press_task or should be cleared now.
        if self.is_dragging_initiated: # If it was a drag, it's consumed.
            self.touch_start_points.pop(point.id, None)
        # If no tasks are pending to evaluate taps, and it wasn't a drag, it might be an unhandled release.
        elif not self.task_mgr.hasTaskNamed(self._finalize_tap_task_name):
             self.touch_start_points.pop(point.id, None)


class TouchApp(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)

        # Disable default mouse camera control
        self.disableMouse()
        self.camera.setPos(0, -30, 6) # Move camera back to see 2D elements
        self.cam.node().getDisplayRegion(0).setSort(20) # Ensure 2D is rendered on top

        # --- UI Elements & Logic Instances ---
        self.status_text = OnscreenText(text="Panda3D Touch Demo", pos=(-1.2, 0.9), scale=0.07, align=TextNode.ALeft)
        self.joystick_text = OnscreenText(text="Joystick: X=0.00, Y=0.00", pos=(-1.2, 0.8), scale=0.06, align=TextNode.ALeft)
        self.gesture_text = OnscreenText(text="Gesture: None", pos=(-1.2, 0.7), scale=0.06, align=TextNode.ALeft)

        # 1. Touch Button
        self.button_logic = TouchButtonLogic("my_button", self.on_button_clicked_feedback)
        self.my_button_vis = DirectButton(text="Click Me", scale=0.1, pos=(-0.8, 0, 0.5),
                                          command=self.on_panda_button_click_proxy)
                                          # We'll use mouse events for more control for demo

        # 2. Virtual Joystick
        joystick_visual_radius = 0.15
        joystick_handle_radius = 0.07
        self.joystick_logic = VirtualJoystickLogic(self.on_joystick_move_feedback, visual_radius_units=joystick_visual_radius - joystick_handle_radius)
        
        cm = CardMaker("joystick_base_card")
        cm.setFrame(-joystick_visual_radius, joystick_visual_radius, -joystick_visual_radius, joystick_visual_radius)
        self.joystick_base_vis = NodePath(cm.generate())
        self.joystick_base_vis.reparentTo(self.aspect2d)
        self.joystick_base_vis.setPos(0, 0, 0) # Centered
        self.joystick_base_vis.setColor(0.3, 0.3, 0.3, 1)
        self.joystick_base_center_screen = Vec2(self.joystick_base_vis.getX(self.aspect2d), self.joystick_base_vis.getZ(self.aspect2d))


        cm_handle = CardMaker("joystick_handle_card")
        cm_handle.setFrame(-joystick_handle_radius, joystick_handle_radius, -joystick_handle_radius, joystick_handle_radius)
        self.joystick_handle_vis = NodePath(cm_handle.generate())
        self.joystick_handle_vis.reparentTo(self.joystick_base_vis) # Child of base for relative positioning
        self.joystick_handle_vis.setPos(0,0,0) # Initially at center of base
        self.joystick_handle_vis.setColor(0.8, 0.2, 0.2, 1)
        
        # 3. Gesture Area
        gesture_area_dims = (-0.5, 0.5, -0.5, 0.2) # left, right, bottom, top
        self.gesture_recognizer = GestureRecognizer(self.on_gesture_feedback, self.taskMgr)
        cm_gesture = CardMaker("gesture_area_card")
        cm_gesture.setFrame(gesture_area_dims[0], gesture_area_dims[1], gesture_area_dims[2], gesture_area_dims[3])
        self.gesture_area_vis = NodePath(cm_gesture.generate())
        self.gesture_area_vis.reparentTo(self.aspect2d)
        self.gesture_area_vis.setPos(0.7, 0, -0.5) # Position on screen
        self.gesture_area_vis.setColor(0.2, 0.2, 0.8, 0.5) # Semi-transparent blue
        self.gesture_area_bounds_screen = ( # L, R, B, T in aspect2d coords
            self.gesture_area_vis.getX(self.aspect2d) + gesture_area_dims[0],
            self.gesture_area_vis.getX(self.aspect2d) + gesture_area_dims[1],
            self.gesture_area_vis.getZ(self.aspect2d) + gesture_area_dims[2],
            self.gesture_area_vis.getZ(self.aspect2d) + gesture_area_dims[3],
        )


        # --- Input Handling ---
        self.active_mouse_target = None # 'button', 'joystick', 'gesture_area', None
        self.accept("mouse1", self.handle_mouse_down)
        self.accept("mouse1-up", self.handle_mouse_up)
        self.taskMgr.add(self.mouse_move_task, "mouseMoveTask")

    def get_mouse_pos_aspect2d(self):
        if self.mouseWatcherNode.hasMouse():
            return TouchPoint(id=0, x=self.mouseWatcherNode.getMouseX(), y=self.mouseWatcherNode.getMouseY())
        return None

    def is_point_in_bounds(self, point: TouchPoint, bounds_lrtb):
        return bounds_lrtb[0] <= point.x <= bounds_lrtb[1] and \
               bounds_lrtb[2] <= point.y <= bounds_lrtb[3]

    def handle_mouse_down(self):
        p_screen = self.get_mouse_pos_aspect2d()
        if not p_screen: return

        # Check gesture area first (often largest interactive area)
        if self.is_point_in_bounds(p_screen, self.gesture_area_bounds_screen):
            self.active_mouse_target = 'gesture_area'
            self.gesture_recognizer.handle_touch_down(p_screen)
            self.gesture_area_vis.setColor(0.3,0.3,1,0.6) # Visual feedback
            return

        # Check joystick (distance from center)
        dist_to_joy_center_sq = (p_screen.x - self.joystick_base_center_screen.x)**2 + \
                                (p_screen.y - self.joystick_base_center_screen.y)**2
        if dist_to_joy_center_sq <= (self.joystick_logic.max_displacement_units + 0.07)**2: # Approx visual radius of base
            self.active_mouse_target = 'joystick'
            self.joystick_logic.start_drag(p_screen, self.joystick_base_center_screen)
            self.joystick_handle_vis.setColor(1,0.3,0.3,1) # Active color
            return
        
        # Check button (using Panda3D's own bounds or approximate here)
        # For DirectButton, command is usually enough. For custom, check bounds:
        button_bounds = ( # Approximate bounds for demo
            self.my_button_vis.getX(self.aspect2d) - 0.1 * self.my_button_vis.getScale().x,
            self.my_button_vis.getX(self.aspect2d) + 0.1 * self.my_button_vis.getScale().x,
            self.my_button_vis.getZ(self.aspect2d) - 0.05 * self.my_button_vis.getScale().z, # Text is usually taller
            self.my_button_vis.getZ(self.aspect2d) + 0.05 * self.my_button_vis.getScale().z,
        )
        if self.is_point_in_bounds(p_screen, button_bounds):
            self.active_mouse_target = 'button'
            self.button_logic.handle_press(p_screen)
            self.my_button_vis.setColorScale(0.9, 0.9, 0.9, 1) # Pressed feedback
            return

    def handle_mouse_up(self):
        p_screen = self.get_mouse_pos_aspect2d()
        if not p_screen: p_screen = TouchPoint(0,0,0) # Fallback if mouse exits window before up

        if self.active_mouse_target == 'gesture_area':
            self.gesture_recognizer.handle_touch_up(p_screen)
            self.gesture_area_vis.setColor(0.2,0.2,0.8,0.5) # Reset color
        elif self.active_mouse_target == 'joystick':
            self.joystick_logic.end_drag()
            self.joystick_handle_vis.setPos(0,0,0) # Reset handle
            self.joystick_handle_vis.setColor(0.8,0.2,0.2,1) # Reset color
        elif self.active_mouse_target == 'button':
            self.button_logic.handle_release(p_screen)
            self.my_button_vis.clearColorScale() # Reset color
        
        self.active_mouse_target = None

    def mouse_move_task(self, task):
        if self.mouseWatcherNode.hasMouse():
            p_screen = self.get_mouse_pos_aspect2d()
            if not p_screen: return task.cont

            if self.active_mouse_target == 'gesture_area':
                self.gesture_recognizer.handle_touch_move(p_screen)
            elif self.active_mouse_target == 'joystick':
                self.joystick_logic.drag(p_screen)
                # Update joystick handle visual
                # Calculate displacement relative to joystick base center in screen coords
                dx_screen = p_screen.x - self.joystick_base_center_screen.x
                dy_screen = p_screen.y - self.joystick_base_center_screen.y
                
                # Clamp handle position to joystick_logic's max_displacement_units (visual radius of movement)
                dist = (dx_screen**2 + dy_screen**2)**0.5
                max_disp = self.joystick_logic.max_displacement_units
                
                clamped_x_screen = dx_screen
                clamped_y_screen = dy_screen

                if dist > max_disp:
                    clamped_x_screen = (dx_screen / dist) * max_disp
                    clamped_y_screen = (dy_screen / dist) * max_disp
                
                # The handle is a child of joystick_base_vis, so set local pos
                self.joystick_handle_vis.setPos(clamped_x_screen, 0, clamped_y_screen)


        return task.cont

    def on_panda_button_click_proxy(self):
        # This is called by DirectButton's internal command on release.
        # We use our custom logic via mouse events for more detailed control,
        # but this can be a fallback or primary for simple buttons.
        # print("Panda DirectButton clicked (proxy)")
        # self.button_logic.handle_press(TouchPoint(0,0,0)) # Simulate press/release
        # self.button_logic.handle_release(TouchPoint(0,0,0))
        pass


    # --- Feedback Methods ---
    def on_button_clicked_feedback(self, button_id):
        self.status_text.setText(f"Button '{button_id}' Clicked!")
        print(f"Feedback: Button '{button_id}' Clicked!")

    def on_joystick_move_feedback(self, vec: Vec2):
        self.joystick_text.setText(f"Joystick: X={vec.x:.2f}, Y={vec.y:.2f}")
        # print(f"Feedback: Joystick Vec: {vec}")

    def on_gesture_feedback(self, name, details):
        self.gesture_text.setText(f"Gesture: {name} {details if details else ''}")
        # print(f"Feedback: Gesture: {name} - {details if details else ''}")


app = TouchApp()
app.run()

# How to Run:

# Make sure you have Panda3D installed (pip install panda3d).
# Save the code above as a Python file (e.g., panda_touch_demo.py).
# Run it from your terminal: python panda_touch_demo.py.
# Explanation:

# TouchApp(ShowBase): The main application class.
# Helper Classes (Vec2, TouchPoint): Same as before, for 2D math and touch data.
# Logic Classes (TouchButtonLogic, VirtualJoystickLogic, GestureRecognizer): These handle the state and core mechanics, largely independent of Panda3D rendering.
# The GestureRecognizer now uses Panda3D's taskMgr to schedule delayed tasks for checking long presses and finalizing multi-tap sequences, making it more robust.
# Panda3D UI Elements:
# DirectButton: Used for the clickable button.
# DirectFrame (via CardMaker): Used to create simple visual representations for the joystick base, handle, and gesture area.
# OnScreenText: Displays feedback.
# Input Handling:
# accept("mouse1", ...) and accept("mouse1-up", ...): Panda3D's way to listen for left mouse button clicks.
# mouse_move_task: A task that continuously checks the mouse position for dragging.
# get_mouse_pos_aspect2d(): Gets mouse coordinates in Panda3D's aspect2d space (ranges roughly -1 to 1).
# active_mouse_target: A simple state variable to track which UI element the mouse is currently interacting with (button, joystick, or gesture area). This helps route events correctly.
# Coordinate Management: The joystick and gesture area logic work with screen coordinates. The joystick handle's visual position is updated based on the logic's output.
# Feedback: Callbacks update OnScreenText elements to show the results of interactions.
# This example provides a foundational demonstration. For a full application, you would expand on visuals, add more robust bounds checking, and potentially integrate Panda3D's native touch events if targeting multi-touch devices.
