# expand the Panda3D demo with improved visuals, more robust bounds checking, and integrate Panda3D's native touch event handling to support multi-touch interactions (specifically for a basic pinch gesture). 
# The mouse will continue to function as a fallback, simulating a single touch.

# Here are the key changes:

# Visuals:
# The Touch Button will change its relief (raised/sunken) on press/release.
# The Virtual Joystick base and handle will be represented by flat cards, but the logic for movement will be circular. 
# Colors will change on interaction.
# The Gesture Area will have a clearer visual border.
# Bounds Checking:
# Bounds for the joystick and gesture area will be calculated more precisely based on their on-screen dimensions and positions.
# Circular bounds check for joystick interaction.
# Native Touch Events:
# A new task poll_inputs_task will be added to process both mouse and native Panda3D touch events.
# The system will track multiple touch points, each with a unique ID.
# The GestureRecognizer will be updated to:
# Handle input from a specific touch ID (for single-touch gestures like tap, swipe, long press using the primary touch).
# Detect a basic two-finger pinch gesture (scale change) if two touches are active within its bounds.
# The VirtualJoystickLogic and TouchButtonLogic will primarily react to a single "capturing" touch.
# Input Management:
# The input handling will differentiate between mouse input (simulating touch ID 0) and actual touch inputs.
# A dictionary active_touch_props will track which UI element each active touch ID is currently interacting with.


from direct.showbase.ShowBase import ShowBase
from direct.gui.DirectGui import DirectButton, DirectFrame, OnscreenText, DGG
from panda3d.core import TextNode, CardMaker, NodePath, Vec3, Point3, LineSegs, TransparencyAttrib
from panda3d.core import MouseButton, InputDevice, TouchInfo, InputDeviceManager
from direct.task import Task
import time
import math

# --- Helper Classes ---
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

class TouchPoint: # Represents a touch point in screen space (aspect2d)
    def __init__(self, id, x, y, initial_x=None, initial_y=None):
        self.id = id
        self.x = float(x) 
        self.y = float(y)
        self.initial_x = float(initial_x if initial_x is not None else x)
        self.initial_y = float(initial_y if initial_y is not None else y)
        self.time_down = time.monotonic()

    def __repr__(self):
        return f"TouchPoint(id={self.id}, x={self.x:.2f}, y={self.y:.2f})"

# --- Core Logic Components ---

class TouchButtonLogic:
    def __init__(self, button_id, on_click_callback):
        self.id = button_id
        self.on_click_callback = on_click_callback
        self.is_pressed_by_touch_id = None

    def handle_press(self, point: TouchPoint):
        if self.is_pressed_by_touch_id is None:
            self.is_pressed_by_touch_id = point.id
            return True # Successfully pressed
        return False # Already pressed by another touch

    def handle_release(self, point: TouchPoint):
        if self.is_pressed_by_touch_id == point.id:
            self.is_pressed_by_touch_id = None
            if self.on_click_callback:
                self.on_click_callback(self.id)
            return True # Successfully released
        return False

class VirtualJoystickLogic:
    def __init__(self, on_move_callback, dead_zone_radius_normalized=0.1, movement_radius_units=0.1): # movement_radius is for handle center
        self.on_move_callback = on_move_callback
        self.direction = Vec2(0, 0)
        self.active_touch_id = None
        self.base_center_pos_screen = Vec2(0,0) 
        self.movement_radius_units = movement_radius_units 
        self.dead_zone_radius_normalized = dead_zone_radius_normalized

    def start_drag(self, touch_point_screen: TouchPoint, joystick_base_center_screen: Vec2):
        if self.active_touch_id is None:
            self.active_touch_id = touch_point_screen.id
            self.base_center_pos_screen = joystick_base_center_screen
            self._update_direction(touch_point_screen)
            return True
        return False

    def drag(self, touch_point_screen: TouchPoint):
        if self.active_touch_id == touch_point_screen.id:
            self._update_direction(touch_point_screen)
            return True
        return False

    def end_drag(self, touch_id: int):
        if self.active_touch_id == touch_id:
            self.active_touch_id = None
            self.direction = Vec2(0, 0)
            if self.on_move_callback:
                self.on_move_callback(self.direction)
            return True
        return False

    def _update_direction(self, current_touch_point_screen: TouchPoint):
        dx = current_touch_point_screen.x - self.base_center_pos_screen.x
        dy = current_touch_point_screen.y - self.base_center_pos_screen.y
        
        # Normalize by movement_radius_units (effective radius for handle center)
        norm_x = dx / self.movement_radius_units if self.movement_radius_units else 0
        norm_y = dy / self.movement_radius_units if self.movement_radius_units else 0
        
        norm_vec = Vec2(norm_x, norm_y)
        norm_distance = norm_vec.magnitude()

        if norm_distance > 1.0: # Clamp to edge of movement radius
            norm_vec = norm_vec.normalized()
        
        if norm_distance < self.dead_zone_radius_normalized:
            self.direction = Vec2(0, 0)
        else:
            effective_radius = 1.0 - self.dead_zone_radius_normalized
            if effective_radius <= 0:
                 self.direction = Vec2(0,0)
            else:
                scale = (norm_distance - self.dead_zone_radius_normalized) / effective_radius
                final_vec_normalized = norm_vec.normalized() # Use the clamped/original normalized vector
                self.direction = Vec2(final_vec_normalized.x * min(1.0, scale), 
                                      final_vec_normalized.y * min(1.0, scale))
        
        if self.on_move_callback:
            self.on_move_callback(self.direction)

class GestureRecognizer:
    MAX_TAP_INTERVAL_SEC = 0.3
    MIN_SWIPE_DISTANCE_UNITS = 0.1 
    LONG_PRESS_DURATION_SEC = 0.7
    MIN_PINCH_SCALE_DIFF = 0.05 # Minimum change in scale to register a pinch

    def __init__(self, on_gesture_callback, task_mgr):
        self.on_gesture_callback = on_gesture_callback
        self.task_mgr = task_mgr
        
        # Per-touch state for single-touch gestures
        self.single_touch_gestures_state = {} # {touch_id: {'start_time', 'start_point', 'is_dragging', 'tap_count', 'last_tap_time'}}
        
        # State for two-finger pinch
        self.pinch_touch_ids = []
        self.pinch_initial_dist = 0
        self.pinch_initial_center = None

        self._long_press_task_prefix = "longPressCheckTask_"
        self._finalize_tap_task_prefix = "finalizeTapGestureTask_"

    def _emit_gesture(self, name, details=None):
        if self.on_gesture_callback:
            self.on_gesture_callback(name, details)

    def _clear_pending_tasks_for_touch(self, touch_id):
        self.task_mgr.remove(f"{self._long_press_task_prefix}{touch_id}")
        self.task_mgr.remove(f"{self._finalize_tap_task_prefix}{touch_id}")

    def _reset_tap_sequence_for_touch(self, touch_id):
        if touch_id in self.single_touch_gestures_state:
            self.single_touch_gestures_state[touch_id]['tap_count'] = 0
        self.task_mgr.remove(f"{self._finalize_tap_task_prefix}{touch_id}")

    def _long_press_check_task(self, task):
        name = task.getName()
        touch_id = int(name.split("_")[-1])
        if touch_id in self.single_touch_gestures_state:
            state = self.single_touch_gestures_state[touch_id]
            if not state['is_dragging']:
                 self._emit_gesture("Long Press", {"touch_id": touch_id})
                 self.single_touch_gestures_state.pop(touch_id, None) # Consume
                 self._reset_tap_sequence_for_touch(touch_id)
        return Task.done

    def _finalize_tap_gesture_task(self, task):
        name = task.getName()
        touch_id = int(name.split("_")[-1])
        if touch_id in self.single_touch_gestures_state:
            state = self.single_touch_gestures_state[touch_id]
            if state['tap_count'] > 0:
                if state['tap_count'] == 1: self._emit_gesture("Tap", {"touch_id": touch_id})
                elif state['tap_count'] == 2: self._emit_gesture("Double Tap", {"touch_id": touch_id})
                elif state['tap_count'] >= 3: self._emit_gesture("Triple Tap", {"touch_id": touch_id})
            
            # Reset tap count but keep state for potential drag after tap sequence ends.
            state['tap_count'] = 0 
        return Task.done

    def handle_touch_down(self, point: TouchPoint, all_active_touches: dict):
        touch_id = point.id
        self._clear_pending_tasks_for_touch(touch_id)
        
        self.single_touch_gestures_state[touch_id] = {
            'start_time': time.monotonic(),
            'start_point': point, # Store the TouchPoint object
            'current_point': point,
            'is_dragging': False,
            'tap_count': 0,
            'last_tap_time': 0
        }
        
        self.task_mgr.doMethodLater(self.LONG_PRESS_DURATION_SEC, 
                                   self._long_press_check_task, 
                                   f"{self._long_press_task_prefix}{touch_id}")

        # Pinch detection (basic):
        active_gesture_area_touches = [t for t_id, t in all_active_touches.items() if t_id in self.single_touch_gestures_state] # Touches currently in gesture area
        if len(active_gesture_area_touches) == 2 and not self.pinch_touch_ids:
            self.pinch_touch_ids = [t.id for t in active_gesture_area_touches]
            p1 = active_gesture_area_touches[0]
            p2 = active_gesture_area_touches[1]
            self.pinch_initial_dist = math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)
            self.pinch_initial_center = Vec2((p1.x + p2.x)/2, (p1.y + p2.y)/2)
            self._emit_gesture("Pinch Start", {"touch_ids": self.pinch_touch_ids})


    def handle_touch_move(self, point: TouchPoint, all_active_touches: dict):
        touch_id = point.id
        if touch_id not in self.single_touch_gestures_state: return

        state = self.single_touch_gestures_state[touch_id]
        state['current_point'] = point
        start_point = state['start_point']
        
        dx = point.x - start_point.x
        dy = point.y - start_point.y
        dist_sq = dx*dx + dy*dy

        if not state['is_dragging'] and dist_sq > (0.01)**2: # Small movement threshold
            state['is_dragging'] = True
            self.task_mgr.remove(f"{self._long_press_task_prefix}{touch_id}") # Movement cancels long press

        # Pinch move detection
        if len(self.pinch_touch_ids) == 2 and touch_id in self.pinch_touch_ids:
            # Get the two points involved in the pinch
            p1_id, p2_id = self.pinch_touch_ids
            # One of them is 'point', the other is from all_active_touches
            p1_current = all_active_touches.get(p1_id)
            p2_current = all_active_touches.get(p2_id)

            if p1_current and p2_current and self.pinch_initial_dist > 1e-5:
                current_dist = math.sqrt((p1_current.x - p2_current.x)**2 + (p1_current.y - p2_current.y)**2)
                scale = current_dist / self.pinch_initial_dist
                if abs(scale - 1.0) > self.MIN_PINCH_SCALE_DIFF: # Emit only on significant change
                     self._emit_gesture("Pinch Move", {"scale": round(scale, 2), "touch_ids": self.pinch_touch_ids})
                     # For continuous pinch, might update initial_dist here or manage relative scale

    def handle_touch_up(self, point: TouchPoint, all_active_touches: dict):
        touch_id = point.id
        if touch_id not in self.single_touch_gestures_state: return
        
        state = self.single_touch_gestures_state[touch_id]
        self.task_mgr.remove(f"{self._long_press_task_prefix}{touch_id}")
        
        duration_sec = time.monotonic() - state['start_time']
        start_p = state['start_point'] # This is a TouchPoint object
        end_p = state['current_point'] # Use the last known position for this touch

        if not state['is_dragging'] and duration_sec < self.LONG_PRESS_DURATION_SEC:
            # Tap related
            current_time_mono = time.monotonic()
            if current_time_mono - state.get('last_tap_time', 0) < self.MAX_TAP_INTERVAL_SEC and state['tap_count'] > 0:
                state['tap_count'] += 1
            else:
                self._reset_tap_sequence_for_touch(touch_id) # Clears pending finalize task
                state['tap_count'] = 1
            state['last_tap_time'] = current_time_mono
            
            self.task_mgr.doMethodLater(self.MAX_TAP_INTERVAL_SEC, 
                                       self._finalize_tap_gesture_task, 
                                       f"{self._finalize_tap_task_prefix}{touch_id}")
        
        elif state['is_dragging']:
            dx = end_p.x - start_p.x
            dy = end_p.y - start_p.y
            distance = (dx**2 + dy**2)**0.5

            if distance > self.MIN_SWIPE_DISTANCE_UNITS:
                direction = ""
                if abs(dx) > abs(dy): direction = "Right" if dx > 0 else "Left"
                else: direction = "Down" if dy > 0 else "Up"
                self._emit_gesture(f"Swipe {direction}", {"distance": round(distance,2), "touch_id": touch_id})
            else: # Not long enough for swipe, just a drag end
                self._emit_gesture("Drag End", {"dx": round(dx,2), "dy": round(dy,2), "touch_id": touch_id})
            
            self.single_touch_gestures_state.pop(touch_id, None) # Consume state
            self._reset_tap_sequence_for_touch(touch_id) # Clear tap state too

        # Pinch end detection
        if touch_id in self.pinch_touch_ids:
            self.pinch_touch_ids.remove(touch_id)
            if not self.pinch_touch_ids: # If both pinch fingers are up or one is left alone
                self._emit_gesture("Pinch End")
                self.pinch_initial_dist = 0
                self.pinch_initial_center = None
        
        # If tap not finalized by task and not a drag, it might be an abandoned touch
        # The finalize_tap_gesture_task or drag logic should consume single_touch_gestures_state[touch_id]
        # If it's still here after some timeout, it might need cleanup.
        # For now, we rely on explicit consumption or overwrite on next down.
        if not state['is_dragging'] and not self.task_mgr.hasTaskNamed(f"{self._finalize_tap_task_prefix}{touch_id}"):
            # If it wasn't a drag, and no tap is pending, remove its state
            self.single_touch_gestures_state.pop(touch_id, None)


class TouchApp(ShowBase):
    MOUSE_SIM_TOUCH_ID = 0 # Special ID for mouse simulated touch

    def __init__(self):
        ShowBase.__init__(self)
        self.setupMouse(self.win) # Important for enabling mouse watcher for touches
        self.disableMouse() # Disable default camera control with mouse
        
        self.camera.setPos(0, -35, 0) 
        self.cam.node().getDisplayRegion(0).setSort(20)

        # --- UI Elements & Logic ---
        self.status_text = OnscreenText(text="Panda3D Multi-Touch Demo", pos=(-1.25, 0.9), scale=0.06, align=TextNode.ALeft, fg=(1,1,1,1))
        self.joystick_text = OnscreenText(text="Joystick: X=0.00, Y=0.00", pos=(-1.25, 0.82), scale=0.05, align=TextNode.ALeft, fg=(1,1,1,1))
        self.gesture_text = OnscreenText(text="Gesture: None", pos=(-1.25, 0.74), scale=0.05, align=TextNode.ALeft, fg=(1,1,1,1))
        self.touch_debug_texts = {} # For displaying individual touch info

        # 1. Touch Button
        self.button_logic = TouchButtonLogic("my_button", self.on_button_clicked_feedback)
        self.my_button_vis = DirectButton(text="Click/Touch", scale=0.08, pos=(-0.9, 0, 0.5),
                                          relief=DGG.RAISED, borderWidth=(0.01, 0.01),
                                          frameColor=((0.6,0.6,0.6,1), (0.7,0.7,0.7,1), (0.8,0.8,0.8,1), (0.5,0.5,0.5,1)))
                                          # command=self.on_panda_button_click_proxy # We handle via poll_inputs_task
        button_frameSize = self.my_button_vis.getBounds() # This gives L,R,B,T in button's local space
        # Approximate screen bounds (aspect2d)
        btn_s = self.my_button_vis.getScale()
        btn_p = self.my_button_vis.getPos(self.aspect2d)
        self.button_bounds_screen = (
            btn_p.x + button_frameSize[0] * btn_s.x, btn_p.x + button_frameSize[1] * btn_s.x,
            btn_p.z + button_frameSize[2] * btn_s.z, btn_p.z + button_frameSize[3] * btn_s.z
        )


        # 2. Virtual Joystick
        joystick_base_radius_units = 0.15
        joystick_handle_radius_units = 0.06
        joystick_movement_radius = joystick_base_radius_units - joystick_handle_radius_units
        self.joystick_logic = VirtualJoystickLogic(self.on_joystick_move_feedback, 
                                                   movement_radius_units=joystick_movement_radius)
        
        cm_base = CardMaker("joystick_base_card")
        cm_base.setFrame(-joystick_base_radius_units, joystick_base_radius_units, -joystick_base_radius_units, joystick_base_radius_units)
        self.joystick_base_vis = NodePath(cm_base.generate())
        self.joystick_base_vis.reparentTo(self.aspect2d)
        self.joystick_base_vis.setPos(0, 0, -0.1) # Centered horizontally, lower on screen
        self.joystick_base_vis.setColor(0.4, 0.4, 0.45, 1)
        self.joystick_base_center_screen = Vec2(self.joystick_base_vis.getX(self.aspect2d), self.joystick_base_vis.getZ(self.aspect2d))

        cm_handle = CardMaker("joystick_handle_card")
        cm_handle.setFrame(-joystick_handle_radius_units, joystick_handle_radius_units, -joystick_handle_radius_units, joystick_handle_radius_units)
        self.joystick_handle_vis = NodePath(cm_handle.generate())
        self.joystick_handle_vis.reparentTo(self.joystick_base_vis)
        self.joystick_handle_vis.setPos(0,0,0.001) # Slightly above base for draw order
        self.joystick_handle_vis.setColor(0.9, 0.3, 0.3, 1)
        
        self.joystick_bounds_screen_radius_sq = (joystick_base_radius_units * 1.1)**2 # Slightly larger for easier activation

        # 3. Gesture Area
        self.gesture_recognizer = GestureRecognizer(self.on_gesture_feedback, self.taskMgr)
        gesture_area_size = (0.8, 0.6) # width, height
        self.gesture_area_vis = DirectFrame(frameSize=(-gesture_area_size[0]/2, gesture_area_size[0]/2, 
                                                       -gesture_area_size[1]/2, gesture_area_size[1]/2),
                                            frameColor=(0.2, 0.25, 0.7, 0.4),
                                            pos=(0.7, 0, -0.5),
                                            parent=self.aspect2d,
                                            borderWidth=(0.01,0.01),
                                            relief=DGG.SUNKEN)
        g_pos = self.gesture_area_vis.getPos(self.aspect2d)
        g_fs = self.gesture_area_vis['frameSize']
        self.gesture_area_bounds_screen = (g_pos.x + g_fs[0], g_pos.x + g_fs[1], g_pos.z + g_fs[2], g_pos.z + g_fs[3])

        # 1) Find & attach any touchscreens
        self.dev_mgr = InputDeviceManager.getGlobalPtr()
        touch_devs = self.dev_mgr.getDevices(InputDevice.DeviceClass.touch)
        for dev in touch_devs:
            self.attachInputDevice(dev, prefix=dev.name)

        # 2) Tell the mouseWatcherNode to watch for touch events on that device
        #    (mouseWatcherNode will now generate events like "devname-touch", etc.)
        #    You can bind to those via self.accept(dev.name + "-touch", …)

        # Skip calling hasTouch(); instead listen for the touch events you attached.

        # --- Input State & Handling ---
        self.previous_touches_state = {} # {touch_id: TouchPoint}
        self.active_touch_props = {}   # {touch_id: {'target': 'button'/'joystick'/'gesture_area', 'target_obj': obj}}
        self.taskMgr.add(self.poll_inputs_task, "pollInputsTask")
        
        self.accept("escape", self.userExit) # Allow Esc to exit

    def get_aspect2d_touch_point(self, touch_info: TouchInfo, initial_x=None, initial_y=None):
        # Panda's touch coords are 0-1 from top-left. Convert to aspect2d style (-1 to 1).
        # This needs calibration if window aspect ratio is not 1:1 with display region.
        # Assuming fullscreen or consistent aspect ratio for simplicity.
        # Y is inverted for aspect2d.
        # This also assumes the touch input is for the main window/display region.
        
        # Simpler approach: use mouseWatcherNode.getMouseX/Y which are already in aspect2d space for touches too.
        # This is more reliable if mouseWatcherNode is properly configured for the display region.
        return TouchPoint(id=touch_info.getId(), 
                          x=touch_info.getX(), # These are already in -1 to 1 relative to display region
                          y=touch_info.getY(), # Y is already -1 (bottom) to 1 (top)
                          initial_x=initial_x, 
                          initial_y=initial_y)


    def poll_inputs_task(self, task):
        current_touches_on_screen = {} # {touch_id: TouchPoint from TouchInfo}
        
        # Process native touches
        if hasattr(self.mouseWatcherNode, 'hasTouch') and self.mouseWatcherNode.hasTouch():
            num_touches = self.mouseWatcherNode.getNumTouches()
            for i in range(num_touches):
                t_info = self.mouseWatcherNode.getTouch(i)
                
                # Reconstruct TouchPoint, preserving initial_x/y if known
                prev_touch = self.previous_touches_state.get(t_info.getId())
                initial_x = prev_touch.initial_x if prev_touch else t_info.getX()
                initial_y = prev_touch.initial_y if prev_touch else t_info.getY()

                p_screen = self.get_aspect2d_touch_point(t_info, initial_x, initial_y)
                current_touches_on_screen[p_screen.id] = p_screen
        
        # Mouse fallback (if no native touches are active OR if we want to always allow mouse)
        # For this demo, mouse acts if no true touches, or can be primary if desired.
        # To simplify, let's process mouse if no native touches OR if it's already interacting.
        process_mouse = True # Adjust this flag for exclusive touch or mixed mode.
        
        if process_mouse and self.mouseWatcherNode.hasMouse():
            # Check if mouse button is pressed
            is_mouse_down = self.mouseWatcherNode.isButtonDown(MouseButton.one())
            mouse_id = self.MOUSE_SIM_TOUCH_ID

            if is_mouse_down:
                mx, my = self.mouseWatcherNode.getMouseX(), self.mouseWatcherNode.getMouseY()
                prev_touch = self.previous_touches_state.get(mouse_id)
                initial_x = prev_touch.initial_x if prev_touch else mx
                initial_y = prev_touch.initial_y if prev_touch else my
                
                current_touches_on_screen[mouse_id] = TouchPoint(mouse_id, mx, my, initial_x, initial_y)
            elif mouse_id in self.previous_touches_state: 
                # Mouse was down, now up. Add it to current_touches_on_screen with TFUp flag conceptually.
                # The main dispatch logic below will see it's not in current_touches_on_screen if mouse is up.
                pass


        # --- Compare with previous state to find new_down, moved, released ---
        newly_down_touches = []
        moved_touches = []
        
        for t_id, current_p in current_touches_on_screen.items():
            if t_id not in self.previous_touches_state:
                newly_down_touches.append(current_p)
            else:
                # Could add a small epsilon for move detection if raw TouchInfo flags aren't used
                moved_touches.append(current_p) 

        released_touches_ids = [t_id for t_id in self.previous_touches_state if t_id not in current_touches_on_screen]

        # --- Dispatch events to logic components ---

        # Handle newly down touches (capture targets)
        for p_down in newly_down_touches:
            # Gesture area capture (highest priority for multi-touch)
            if self.is_point_in_bounds(p_down, self.gesture_area_bounds_screen):
                self.active_touch_props[p_down.id] = {'target': 'gesture_area', 'target_obj': self.gesture_recognizer}
                self.gesture_recognizer.handle_touch_down(p_down, current_touches_on_screen)
                self.gesture_area_vis['frameColor'] = (0.3,0.35,0.8,0.5) # Active feedback
                continue # Captured by gesture area

            # Joystick capture
            dist_to_joy_center_sq = (p_down.x - self.joystick_base_center_screen.x)**2 + \
                                    (p_down.y - self.joystick_base_center_screen.y)**2
            if dist_to_joy_center_sq <= self.joystick_bounds_screen_radius_sq:
                if self.joystick_logic.start_drag(p_down, self.joystick_base_center_screen):
                    self.active_touch_props[p_down.id] = {'target': 'joystick', 'target_obj': self.joystick_logic}
                    self.joystick_handle_vis.setColor(1,0.4,0.4,1)
                continue # Captured or attempted capture by joystick

            # Button capture
            if self.is_point_in_bounds(p_down, self.button_bounds_screen):
                if self.button_logic.handle_press(p_down):
                    self.active_touch_props[p_down.id] = {'target': 'button', 'target_obj': self.button_logic}
                    self.my_button_vis['relief'] = DGG.SUNKEN
                continue

        # Handle moved touches
        for p_move in moved_touches:
            if p_move.id in self.active_touch_props:
                props = self.active_touch_props[p_move.id]
                if props['target'] == 'gesture_area':
                    props['target_obj'].handle_touch_move(p_move, current_touches_on_screen)
                elif props['target'] == 'joystick':
                    if props['target_obj'].drag(p_move):
                        # Update joystick handle visual
                        # Logic coords are -1 to 1. Visual coords are relative to joystick base.
                        dx_logic = self.joystick_logic.direction.x 
                        dy_logic = self.joystick_logic.direction.y
                        # Scale by movement radius for visual position
                        vis_x = dx_logic * self.joystick_logic.movement_radius_units
                        vis_y = dy_logic * self.joystick_logic.movement_radius_units
                        self.joystick_handle_vis.setPos(vis_x, 0, vis_y)


        # Handle released touches
        for t_id_up in released_touches_ids:
            # Get the last known point for this touch_id
            p_up = self.previous_touches_state.get(t_id_up)
            if not p_up: continue # Should not happen if logic is correct

            if t_id_up in self.active_touch_props:
                props = self.active_touch_props[t_id_up]
                if props['target'] == 'gesture_area':
                    props['target_obj'].handle_touch_up(p_up, current_touches_on_screen) # Pass last known position
                    # Check if any other touch is still on gesture area
                    is_gesture_area_still_active = any(
                        other_id in self.active_touch_props and self.active_touch_props[other_id]['target'] == 'gesture_area'
                        for other_id in current_touches_on_screen
                    )
                    if not is_gesture_area_still_active:
                         self.gesture_area_vis['frameColor'] = (0.2,0.25,0.7,0.4) # Reset if no touches left
                
                elif props['target'] == 'joystick':
                    if props['target_obj'].end_drag(t_id_up):
                        self.joystick_handle_vis.setPos(0,0,0.001)
                        self.joystick_handle_vis.setColor(0.9,0.3,0.3,1)
                
                elif props['target'] == 'button':
                    if props['target_obj'].handle_release(p_up):
                         self.my_button_vis['relief'] = DGG.RAISED
                
                del self.active_touch_props[t_id_up]


        # Update previous_touches_state for next frame
        self.previous_touches_state = current_touches_on_screen.copy()
        
        # Update debug touch texts
        for i in range(max(5, len(self.touch_debug_texts))): # Max 5 debug lines, or clear old ones
            t_id_to_display = i+1 # Common touch IDs start from 1, mouse is 0
            if i == self.MOUSE_SIM_TOUCH_ID: t_id_to_display = self.MOUSE_SIM_TOUCH_ID # show mouse if active

            if t_id_to_display in current_touches_on_screen:
                p = current_touches_on_screen[t_id_to_display]
                text = f"T{p.id}: ({p.x:.2f}, {p.y:.2f})"
                if p.id in self.active_touch_props:
                    text += f" -> {self.active_touch_props[p.id]['target']}"
                if i not in self.touch_debug_texts:
                    self.touch_debug_texts[i] = OnscreenText(text=text, pos=(-1.25, 0.60 - i * 0.05), scale=0.04, fg=(1,1,0,1), align=TextNode.ALeft)
                else:
                    self.touch_debug_texts[i].setText(text)
                self.touch_debug_texts[i].show()
            elif i in self.touch_debug_texts:
                 self.touch_debug_texts[i].hide()


        return task.cont

    def is_point_in_bounds(self, point: TouchPoint, bounds_lrtb): # Left, Right, Bottom, Top
        return bounds_lrtb[0] <= point.x <= bounds_lrtb[1] and \
               bounds_lrtb[2] <= point.y <= bounds_lrtb[3]

    # --- Feedback Methods ---
    def on_button_clicked_feedback(self, button_id):
        self.status_text.setText(f"Button '{button_id}' Clicked!")
        # print(f"Feedback: Button '{button_id}' Clicked!")

    def on_joystick_move_feedback(self, vec: Vec2):
        self.joystick_text.setText(f"Joystick: X={vec.x:.2f}, Y={vec.y:.2f}")

    def on_gesture_feedback(self, name, details):
        detail_str = ""
        if details:
            if isinstance(details, dict):
                detail_str = ", ".join(f"{k}:{v}" for k,v in details.items())
            else:
                detail_str = str(details)
        self.gesture_text.setText(f"Gesture: {name} {detail_str}")


app = TouchApp()
app.run()

# This enhanced script now polls for native Panda3D touch events and mouse input. 
# The GestureRecognizer has been updated to handle per-touch state for single-touch gestures and includes a basic two-finger pinch detection. 
# Visual feedback for button presses and joystick interaction has also been improved. The bounds checking is more explicitly tied to the screen positions and sizes of the UI elements.
# You can run this script to test mouse interactions and, if you have a touch-enabled device with Panda3D properly configured for its touch input, multi-touch interactions like pinch.
