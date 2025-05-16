# This Python code provides classes for TouchButton, VirtualJoystick, and a GestureRecognizer. 
# It also includes a conceptual TouchInputSystem to illustrate how these might be managed. 
# The gesture recognition logic is simplified but captures the essence of tracking points, times, and distances to differentiate gestures. 
# Mouse fallback is also conceptually included.
# You would integrate these logic components with a specific Python graphics or game library (like Ursina, Pygame, Kivy, etc.) 
# to handle the actual rendering and to feed input events (mouse clicks, touch coordinates) into this system. 
# The Python library would provide the on-screen coordinates, and you'd implement bounds checking for buttons and joystick areas.


import time
import math # For more advanced geometry if needed (e.g., rotation)

# --- Helper Classes ---
class Vec2:
    """A simple 2D vector class, similar to what Ursina provides."""
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
    """Represents a single touch point with an ID and coordinates."""
    def __init__(self, id, x, y):
        self.id = id
        self.x = float(x)
        self.y = float(y)

    def __repr__(self):
        return f"TouchPoint(id={self.id}, x={self.x:.1f}, y={self.y:.1f})"

# --- Core Logic Components ---

class TouchButton:
    """
    Represents a touchable button that triggers a callback on click.
    In a real system, this would also have bounds for hit detection.
    """
    def __init__(self, button_id, on_click_callback):
        self.id = button_id
        self.on_click_callback = on_click_callback
        self.is_pressed = False
        # Visual feedback (e.g., scale tweens) would be handled by the rendering engine.

    def handle_press(self, point: TouchPoint):
        """Called when the button is pressed."""
        self.is_pressed = True
        # print(f"Button '{self.id}' pressed at ({point.x}, {point.y})")
        # Here, one might trigger an animation (e.g., button.animate_scale(1.1)).

    def handle_release(self, point: TouchPoint):
        """Called when the button is released."""
        if self.is_pressed:
            self.is_pressed = False
            # print(f"Button '{self.id}' released.")
            if self.on_click_callback:
                self.on_click_callback(self.id)
            # Here, one might trigger an animation (e.g., button.animate_scale(1.0)).

class VirtualJoystick:
    """
    Represents an on-screen virtual joystick.
    Reports a normalized direction vector.
    """
    def __init__(self, on_move_callback, dead_zone_radius=0.1, max_displacement=50.0): # max_displacement in screen units
        self.on_move_callback = on_move_callback
        self.direction = Vec2(0, 0)
        self.is_dragging = False
        self.base_center_pos = Vec2(0,0) # Center of the joystick base on screen
        self.max_displacement = max_displacement # Effective radius for normalization
        self.dead_zone_radius_normalized = dead_zone_radius # Normalized dead zone (0.0 to 1.0)
        # Handle size and visual aspects would be part of the rendering.

    def start_drag(self, touch_point: TouchPoint, joystick_center_pos: Vec2):
        """
        Call when a touch starts on the joystick.
        joystick_center_pos is the screen coordinate of the joystick's center.
        """
        self.is_dragging = True
        self.base_center_pos = joystick_center_pos
        self._update_direction(touch_point)
        # print(f"Joystick drag started from {touch_point} with base {joystick_center_pos}")

    def drag(self, touch_point: TouchPoint):
        """Call when an active touch on the joystick moves."""
        if not self.is_dragging:
            return
        self._update_direction(touch_point)

    def end_drag(self):
        """Call when the touch on the joystick is released."""
        if not self.is_dragging:
            return
        self.is_dragging = False
        self.direction = Vec2(0, 0)
        if self.on_move_callback:
            self.on_move_callback(self.direction)
        # print("Joystick drag ended.")

    def _update_direction(self, current_touch_point: TouchPoint):
        dx = current_touch_point.x - self.base_center_pos.x
        dy = current_touch_point.y - self.base_center_pos.y

        current_displacement_vec = Vec2(dx, dy)
        distance_from_center = current_displacement_vec.magnitude()

        # Normalize by max_displacement
        norm_x = dx / self.max_displacement if self.max_displacement else 0
        norm_y = dy / self.max_displacement if self.max_displacement else 0
        
        norm_vec = Vec2(norm_x, norm_y)
        norm_distance = norm_vec.magnitude()

        if norm_distance > 1.0: # Clamp to edge
            norm_vec = norm_vec.normalized()
        
        if norm_distance < self.dead_zone_radius_normalized:
            self.direction = Vec2(0, 0)
        else:
            # Scale vector outside deadzone
            # This maps the range [dead_zone, 1.0] to [0, 1.0]
            effective_radius = 1.0 - self.dead_zone_radius_normalized
            if effective_radius <= 0: # Avoid division by zero if dead_zone is 1 or more
                 self.direction = Vec2(0,0)
            else:
                scale = (norm_distance - self.dead_zone_radius_normalized) / effective_radius
                final_vec_normalized = norm_vec.normalized()
                self.direction = Vec2(final_vec_normalized.x * min(1.0, scale), 
                                      final_vec_normalized.y * min(1.0, scale))
        
        if self.on_move_callback:
            self.on_move_callback(self.direction)

class GestureRecognizer:
    """
    Recognizes various touch gestures like taps, swipes, pinch, etc.
    This is a simplified version of the logic in GestureArea.tsx.
    A robust implementation requires careful state management and timing.
    """
    MAX_TAP_INTERVAL_SEC = 0.3
    MIN_SWIPE_DISTANCE_UNITS = 30
    LONG_PRESS_DURATION_SEC = 0.7

    def __init__(self, on_gesture_callback):
        self.on_gesture_callback = on_gesture_callback
        
        self.touch_start_time_mono = 0.0  # Monotonic time
        self.touch_start_points = {}      # Key: touch_id, Value: TouchPoint
        self.last_tap_time_mono = 0.0
        self.tap_count = 0
        self.is_dragging_initiated = False # True if movement occurred after touch down
        self.long_press_pending = False

        # For multi-tap differentiation (single, double, triple)
        self._tap_timeout_event = None # Placeholder for a timed event (e.g., using a scheduler)

    def _emit_gesture(self, name, details=None):
        if self.on_gesture_callback:
            self.on_gesture_callback(name, details)
        # print(f"Gesture: {name}, Details: {details if details else ''}")

    def _reset_tap_sequence(self):
        self.tap_count = 0
        if self._tap_timeout_event:
            # Cancel pending tap evaluation
            # In a game loop, you might remove a scheduled function call
            self._tap_timeout_event = None 

    def _schedule_tap_evaluation(self):
        # This function would typically be called after a potential tap.
        # It waits for MAX_TAP_INTERVAL_SEC to see if more taps occur.
        # In a real system, use a delay mechanism (e.g., Ursina's invoke() or threading.Timer)
        # For this example, we'll simulate this logic more directly in handle_touch_up.
        
        # Simulate the timeout effect: if this method was truly delayed
        if self._tap_timeout_event == "pending_final_tap_check": # Check if it's the scheduled execution
            if self.tap_count == 1 and len(self.touch_start_points) == 1: self._emit_gesture("Tap")
            elif self.tap_count == 2 and len(self.touch_start_points) == 1: self._emit_gesture("Double Tap")
            elif self.tap_count >= 3 and len(self.touch_start_points) == 1: self._emit_gesture("Triple Tap")
            elif self.tap_count == 1 and len(self.touch_start_points) == 2: self._emit_gesture("Two-Finger Tap")
            elif self.tap_count == 1 and len(self.touch_start_points) == 3: self._emit_gesture("Three-Finger Tap")
            self._reset_tap_sequence() # Clear for next sequence
            self.touch_start_points.clear() # Consume points after tap gesture emitted
            
    def handle_touch_down(self, active_touches: list[TouchPoint]):
        """
        Process new touch(es) starting.
        active_touches: A list of all currently active TouchPoint objects on the screen.
        """
        current_time_mono = time.monotonic()
        self.is_dragging_initiated = False
        self.long_press_pending = False
        
        # If it's a new primary touch (or set of touches), reset previous gesture state.
        if not self.touch_start_points: # No existing gesture being tracked
            self.touch_start_time_mono = current_time_mono
            self.touch_start_points = {t.id: t for t in active_touches}
            self._reset_tap_sequence()

            if len(self.touch_start_points) == 1:
                self.long_press_pending = True # Check for long press in update or on touch_up
        else:
            # Additional fingers added to an existing gesture - could be for pinch/rotate start
            for t in active_touches:
                if t.id not in self.touch_start_points:
                    self.touch_start_points[t.id] = t
            self.long_press_pending = False # Multi-touch usually cancels single-finger long press

    def handle_touch_move(self, active_touches: list[TouchPoint]):
        """
        Process movement of active touch(es).
        active_touches: A list of all currently active TouchPoint objects on the screen.
        """
        if not self.touch_start_points: return

        # Check if significant movement occurred since touch_down
        # (More robust check would compare current positions to start_positions)
        self.is_dragging_initiated = True 
        self.long_press_pending = False # Movement cancels long press

        # Update current positions of tracked touches
        current_touch_points_dict = {t.id: t for t in active_touches}

        # Multi-finger gesture logic (e.g., Pinch, Rotate)
        if len(self.touch_start_points) >= 2 and len(current_touch_points_dict) >= 2:
            # Get IDs of the first two starting points for simplicity
            tracked_ids = list(self.touch_start_points.keys())[:2]
            
            p1_start = self.touch_start_points.get(tracked_ids[0])
            p2_start = self.touch_start_points.get(tracked_ids[1])
            p1_current = current_touch_points_dict.get(tracked_ids[0])
            p2_current = current_touch_points_dict.get(tracked_ids[1])

            if p1_start and p2_start and p1_current and p2_current:
                dist_start_sq = (p2_start.x - p1_start.x)**2 + (p2_start.y - p1_start.y)**2
                dist_current_sq = (p2_current.x - p1_current.x)**2 + (p2_current.y - p1_current.y)**2
                
                if dist_start_sq > 1e-6: # Avoid division by zero; 1px^2 threshold
                    scale = (dist_current_sq / dist_start_sq)**0.5
                    if abs(scale - 1.0) > 0.05: # Pinch threshold
                        self._emit_gesture("Pinch", {"scale": round(scale, 2)})
                        # For continuous gestures, update start points to current to measure relative changes
                        # self.touch_start_points[tracked_ids[0]] = p1_current 
                        # self.touch_start_points[tracked_ids[1]] = p2_current

                # Simplified Rotation (requires math.atan2)
                # angle_start_rad = math.atan2(p2_start.y - p1_start.y, p2_start.x - p1_start.x)
                # angle_current_rad = math.atan2(p2_current.y - p1_current.y, p2_current.x - p1_current.x)
                # angle_diff_deg = math.degrees(angle_current_rad - angle_start_rad)
                # if abs(angle_diff_deg) > 5: # Rotate threshold
                #    self._emit_gesture("Rotate", {"angle": round(angle_diff_deg, 1)})
                #    # Update start points for relative rotation
                pass

    def handle_touch_up(self, released_touch_ids: list[int], active_touches: list[TouchPoint]):
        """
        Process lifted touch(es).
        released_touch_ids: List of IDs of touches that were just released.
        active_touches: List of TouchPoint objects that are STILL on the screen.
        """
        if not self.touch_start_points: return

        current_time_mono = time.monotonic()
        duration_sec = current_time_mono - self.touch_start_time_mono
        
        # Check for long press if it was pending and no drag occurred
        if self.long_press_pending and not self.is_dragging_initiated and \
           len(self.touch_start_points) == 1 and (list(self.touch_start_points.keys())[0] in released_touch_ids):
            if duration_sec >= self.LONG_PRESS_DURATION_SEC:
                self._emit_gesture("Long Press")
                self.touch_start_points.clear() # Consume points
                self._reset_tap_sequence()
                return # Long press usually overrides other tap/swipe on that finger

        # Tap-like gestures (if not dragged and short duration)
        if not self.is_dragging_initiated and duration_sec < self.LONG_PRESS_DURATION_SEC:
            # This check should ideally be delayed to distinguish multi-taps accurately.
            # The JS version uses a setTimeout. Here, we simulate its effect.
            
            # If this "up" event matches one of the initial touches
            is_initial_touch_released = any(tid in self.touch_start_points for tid in released_touch_ids)

            if is_initial_touch_released:
                if current_time_mono - self.last_tap_time_mono < self.MAX_TAP_INTERVAL_SEC:
                    self.tap_count += 1
                else: # First tap in a potential sequence or too long since last
                    self._reset_tap_sequence() # Clear previous tap count if timeout occurred
                    self.tap_count = 1
                self.last_tap_time_mono = current_time_mono
                
                # Mark that a tap sequence is in progress and needs final evaluation
                # In a real system, you would schedule _schedule_tap_evaluation to run after MAX_TAP_INTERVAL_SEC
                self._tap_timeout_event = "pending_final_tap_check" 
                
                # If all initial touches are up, we can try to evaluate taps immediately (simplified)
                # A more robust way is to always wait for the timeout for multi-taps
                if not active_touches or all(t.id not in self.touch_start_points for t in active_touches):
                    self._schedule_tap_evaluation() # Simulate immediate timeout for this example if all fingers up
                return # Return to allow timeout mechanism to work for multi-taps


        # Swipe gesture (single finger, dragged)
        elif self.is_dragging_initiated and len(self.touch_start_points) == 1:
            start_touch_id = list(self.touch_start_points.keys())[0]
            if start_touch_id in released_touch_ids: # The dragging finger was lifted
                start_point = self.touch_start_points[start_touch_id]
                # Find the 'up' position of the released touch (need to get it from system input for accuracy)
                # For simulation, let's assume the last point in active_touches before release, or use a placeholder.
                # In a real system, the 'up' event provides the final coordinates.
                # Let's assume the `released_touch_ids` comes with corresponding TouchPoint objects or we find them.
                # For now, we'll assume the original start_point and a hypothetical end_point for distance.
                # This part needs a proper end_point from the input system.
                # For this example, we can't get end_point easily, so swipe logic is illustrative.

                # Example: If input system provided end_point for released_touch_ids[0]
                # end_point = get_final_coords_for_touch(released_touch_ids[0]) 
                # dx = end_point.x - start_point.x
                # dy = end_point.y - start_point.y
                # distance = (dx**2 + dy**2)**0.5
                # if distance > self.MIN_SWIPE_DISTANCE_UNITS:
                #     direction = ""
                #     if abs(dx) > abs(dy): direction = "Right" if dx > 0 else "Left"
                #     else: direction = "Down" if dy > 0 else "Up"
                #     self._emit_gesture(f"Swipe {direction}", {"distance": round(distance,1)})
                pass # Swipe logic placeholder due to end_point ambiguity in this simplified model

        # If all originating touches are now released, reset for the next gesture.
        is_gesture_over = True
        for start_id in self.touch_start_points.keys():
            if any(t.id == start_id for t in active_touches): # Check if any of the *original* touches are still active
                is_gesture_over = False
                break
        
        if is_gesture_over and not self._tap_timeout_event: # Don't clear if waiting for tap eval
            self.touch_start_points.clear()
            self._reset_tap_sequence()


# --- Main Input Handling System (Conceptual) ---
class TouchInputSystem:
    """
    Manages touchable components and processes input events.
    In a game engine like Ursina, this would be part of the engine's input loop.
    """
    def __init__(self):
        self.buttons: list[TouchButton] = []
        self.joystick: VirtualJoystick | None = None
        self.gesture_recognizer: GestureRecognizer | None = None
        
        # Mouse fallback state
        self._mouse_is_down = False
        self._mouse_start_pos = Vec2(0,0)
        self._mouse_target = None # Could be a button, joystick, or gesture_area

    def add_button(self, button: TouchButton): # Would also need button.bounds
        self.buttons.append(button)

    def set_joystick(self, joystick: VirtualJoystick): # Would also need joystick.base_bounds
        self.joystick = joystick

    def set_gesture_recognizer(self, recognizer: GestureRecognizer): # Area bounds needed
        self.gesture_recognizer = recognizer

    # --- MOUSE FALLBACK LOGIC (Simplified) ---
    def on_mouse_button_down(self, x, y, button_name): # button_name "left", "right"
        if button_name != "left": return
        self._mouse_is_down = True
        self._mouse_start_pos = Vec2(x,y)
        
        # Determine target (simplified: gesture recognizer takes precedence if set)
        if self.gesture_recognizer:
            self._mouse_target = self.gesture_recognizer
            self.gesture_recognizer.handle_touch_down([TouchPoint(id=0, x=x, y=y)]) # Mouse as touch ID 0
        # Add logic for buttons and joystick based on their bounds here

    def on_mouse_button_up(self, x, y, button_name):
        if button_name != "left" or not self._mouse_is_down: return
        self._mouse_is_down = False
        
        if self._mouse_target == self.gesture_recognizer and self.gesture_recognizer:
            # Simulate Tap/Click
            self.gesture_recognizer._emit_gesture("Mouse Click") # Simplified direct emission
            # Or more consistently:
            # self.gesture_recognizer.handle_touch_up([0], []) # Assuming mouse was touch ID 0

            # For drag end:
            # dx = x - self._mouse_start_pos.x
            # dy = y - self._mouse_start_pos.y
            # if (dx**2 + dy**2)**0.5 > 10: # Drag threshold
            #     self.gesture_recognizer._emit_gesture("Mouse Drag End", {"dx":dx, "dy":dy})
            pass

        self._mouse_target = None

    def on_mouse_move(self, x, y, dx, dy):
        if not self._mouse_is_down: return
        if self._mouse_target == self.gesture_recognizer and self.gesture_recognizer:
            self.gesture_recognizer.handle_touch_move([TouchPoint(id=0, x=x, y=y)])
            # self.gesture_recognizer._emit_gesture("Mouse Drag", {"dx": dx, "dy": dy}) # Can be noisy

    # --- TOUCH EVENT HANDLING ---
    def process_touch_events(self, touch_events_batch):
        """
        Process a batch of touch events from the OS/Framework.
        Each event in batch could be like:
        {'type': 'down', 'id': 1, 'x': 100, 'y': 150, 'timestamp': ...}
        {'type': 'move', 'id': 1, 'x': 110, 'y': 155, 'timestamp': ...}
        {'type': 'up',   'id': 1, 'x': 110, 'y': 155, 'timestamp': ...}

        This method would update the state of all active touches and then call
        handle_touch_down, handle_touch_move, or handle_touch_up on relevant components.
        This part is highly dependent on the specifics of the input provider.
        For simplicity, we'll assume we get aggregated lists of active/released touches.
        """
        # This is a placeholder for where you'd integrate with a real touch system.
        # Example: if self.gesture_recognizer:
        #   current_active_touches_list = get_current_active_touches_from_system()
        #   released_touch_ids_this_frame = get_released_ids_from_system()
        #
        #   if released_touch_ids_this_frame:
        #       self.gesture_recognizer.handle_touch_up(released_touch_ids_this_frame, current_active_touches_list)
        #   elif new_touches_detected_this_frame: # If new touches appeared
        #       self.gesture_recognizer.handle_touch_down(current_active_touches_list)
        #   elif existing_touches_moved_this_frame:
        #       self.gesture_recognizer.handle_touch_move(current_active_touches_list)
        pass


# --- Example Usage ---
if __name__ == "__main__":
    def print_button_click(button_id):
        print(f"Button '{button_id}' was clicked!")

    def print_joystick_vector(vec: Vec2):
        print(f"Joystick: x={vec.x:.2f}, y={vec.y:.2f}")

    def print_gesture(name, details):
        print(f"Gesture: {name} - {details if details else ''}")

    # Initialize components
    my_button = TouchButton("action_button_1", print_button_click)
    my_joystick = VirtualJoystick(print_joystick_vector, max_displacement=75) # Assume joystick radius 75px
    my_gestures = GestureRecognizer(print_gesture)

    # Setup input system (conceptual)
    input_sys = TouchInputSystem()
    input_sys.add_button(my_button) # Bounds checking would be needed for actual interaction
    input_sys.set_joystick(my_joystick) # Bounds checking for joystick base needed
    input_sys.set_gesture_recognizer(my_gestures)


    print("--- Simulating Mouse Fallback for Gestures (Simplified Click) ---")
    input_sys.on_mouse_button_down(100, 100, "left") # Click at (100,100)
    # ... time passes, mouse moves or not ...
    input_sys.on_mouse_button_up(100, 100, "left")   # Release at (100,100)
    print("")

    print("--- Simulating Single Tap ---")
    # Frame 1: Touch down
    active_touches_frame1 = [TouchPoint(id=1, x=50, y=50)]
    my_gestures.handle_touch_down(active_touches_frame1)
    # Frame 2: Touch up (short duration, no move)
    time.sleep(0.1) # Simulate short delay
    my_gestures.handle_touch_up(released_touch_ids=[1], active_touches=[])
    print("")

    print("--- Simulating Double Tap ---")
    # Tap 1
    active_touches_tap1_down = [TouchPoint(id=1, x=60, y=60)]
    my_gestures.handle_touch_down(active_touches_tap1_down)
    time.sleep(0.05)
    my_gestures.handle_touch_up(released_touch_ids=[1], active_touches=[])
    # Tap 2 (quickly after)
    active_touches_tap2_down = [TouchPoint(id=1, x=60, y=60)] # Can be same ID if system reuses
    my_gestures.handle_touch_down(active_touches_tap2_down)
    time.sleep(0.05)
    my_gestures.handle_touch_up(released_touch_ids=[1], active_touches=[])
    print("")
    
    print("--- Simulating Long Press ---")
    active_touches_lp_down = [TouchPoint(id=1, x=70, y=70)]
    my_gestures.handle_touch_down(active_touches_lp_down)
    time.sleep(my_gestures.LONG_PRESS_DURATION_SEC + 0.1) # Hold for longer than duration
    # Crucially, the check for long press would happen *before* or *during* touch_up if no drag
    # Here, we simulate the check by calling touch_up which internally checks duration if long_press_pending
    my_gestures.handle_touch_up(released_touch_ids=[1], active_touches=[])
    print("")

    print("--- Simulating Pinch (conceptual) ---")
    # Frame 1: Two fingers down
    pinch_f1_down = [TouchPoint(id=1, x=100, y=100), TouchPoint(id=2, x=200, y=100)]
    my_gestures.handle_touch_down(pinch_f1_down)
    # Frame 2: Fingers move closer
    time.sleep(0.1)
    pinch_f2_move = [TouchPoint(id=1, x=120, y=100), TouchPoint(id=2, x=180, y=100)]
    my_gestures.handle_touch_move(pinch_f2_move)
    # Frame 3: Fingers released
    time.sleep(0.1)
    my_gestures.handle_touch_up(released_touch_ids=[1,2], active_touches=[])
    print("")

    print("--- Simulating Joystick Interaction ---")
    # Assume joystick base is at (300,300)
    joystick_center = Vec2(300,300)
    # Touch down on joystick handle area
    my_joystick.start_drag(TouchPoint(id=1, x=320, y=300), joystick_center) # Touched 20px right of center
    # Drag further right
    time.sleep(0.1)
    my_joystick.drag(TouchPoint(id=1, x=350, y=300)) # Dragged to 50px right of center
    # Release
    time.sleep(0.1)
    my_joystick.end_drag()
