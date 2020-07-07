# ============================================================================
# Clocky the Mr. Clock program
# by Tronster, July 2020 ( tronster.com )
#
# Expects a RainbowHAT to be attached to a RaspberryPi's GPIO
# See: https://shop.pimoroni.com/products/rainbow-hat-for-android-things
# See: https://github.com/pimoroni/rainbow-hat
#
# Uses a state machine that passes around state by class type.
#	Start at clock mode: A to go into Nap
#						 B to enter main menu mode
#						 C to enter a "timeout" mode (1 minute countdown)
# 
# MISC:
# Sunset: https://michelanders.blogspot.com/2010/12/calulating-sunrise-and-sunset-in-python.html
# Misc: /usr/lib/python3/dist-packages/rainbowhat/alphanum4.py
# todo: look into threading (audio at lea) https://github.com/hweiguang/rpi-rainbowhat
#
# Bit #s (from right left) used in set_digit_raw(0-3,0b00000000000000):
#       ________________                     bit # ->      ...7654321
#    __ \       1      / __
#   |  \ \____________/ /  |
#   |  | ___   __   __  |  |
#	|  | \ 9\ |  | /11/ | 2|
#   | 6|  \  \|10|/  /  |  |
#   |__| __\_/|__|\_/__ |__|
#       /   7  ||  8   \
#    __ \______||______/ __
#   |  |   / \|  |/ \   |  |
#   | 5|  /12/|13|\14\  |  |
#   |  | /__/_|__|_\__\ | 3|
#   |  |   ___________  |  |
#   |__/ /      4     \ |__|
#       /______________\  
#
# ============================================================================
import colorsys
import math
import rainbowhat as rh			# pylint: disable=import-error
import random
import time


# ----------------------------------------------------------------------------
#	Constants
MAX_LED_DISPLAY_WIDTH = 4	# Number of led display characters
MAX_LEDS = 7				# Number of multicolored LEDs in the "rainbow"


# ----------------------------------------------------------------------------
# Buttons on the the RainbowHAT (static class)
class Buttons():
	led_a	 :int=0
	led_b	 :int=0
	led_c	 :int=0
	trigger_a:bool = False
	trigger_b:bool = False
	trigger_c:bool = False
	def lower_triggers(self):
		self.trigger_a = self.trigger_b = self.trigger_c = False

# ----------------------------------------------------------------------------
#	GLOBALS
buttons  :Buttons = Buttons()
modes = []				# Holds the 'modes' for the logic that runs on the device.
isRunning:bool = True	# Is main loop running?
ms_start :float= None	# float of when a time counter started
ms_now	 :float= None	# float of time now
localtime:time = None	# The current time


# ----------------------------------------------------------------------------
#	Misc helper functions
# ----------------------------------------------------------------------------

# Return the name of the class for a given instance
def GetClassName( instance ):
	return instance.__class__.__name__

# Bounce back and forth on a sub string within a given (LED display) width.
def range_sub_string( msg:str, width:int = MAX_LED_DISPLAY_WIDTH):
	size:int = len(msg)	
	while True:
		index:int = -1
		while index < size-width:
			index += 1
			yield msg[index:index+width]		

# degree is 0 to 360
# returns smooth 0 to 1 based on degree
def get_0to1_from_degree( degree:int ):
	n = math.sin(math.radians( degree ))
	return (n+1)*0.5

# For a 0 to 1 percent range, return a 0 to 1 and back to 0. (e.g, 0.5 is 1)
def get_0to0_from_percent( percent:float ):
	clamp(percent,0,1)
	if percent <= 0.5: return percent*2
	return 1 - ((percent-0.5)*2)

# i is pixel
# sec is # of second 0-59
# returns [r,g,b,brightness]
def get_sin_shine( i:int, sec:int ):
	degree = ((sec*6) + (i*231)) % 360
	amt = 50 * get_0to1_from_degree(degree)
	return [amt, amt, 0, 0.0]

# Fill an array of red,green,blue,brightness values
def pix_array_add(array,r,g,b,brightness=0.05):
	size = len(array)
	for i in range(size):
		array[i] = [sum(n) for n in zip(*[array[i], [r,g,b,brightness]])]

# Blend two red,green,blue,brightness arrays with a weighted value
def pix_array_weighted_blend( a_array:list, b_array:list, a_weight:float ):
	size = len(a_array)
	assert(len(b_array) == size),"Mismatched array sizes!"
	out = []
	for i in range(size):		
		out.append([ 
			(a_weight*b_array[i][0]) + ((1-a_weight)*a_array[i][0]),
			(a_weight*b_array[i][1]) + ((1-a_weight)*a_array[i][1]),
			(a_weight*b_array[i][2]) + ((1-a_weight)*a_array[i][2]),
			(a_weight*b_array[i][3]) + ((1-a_weight)*a_array[i][3])])
	return out

# star is virtual star index # (0 to n)
# sec is # of second 0-59
# size is # of (virtual) pixels to work with
# returns index,[r,g,b,brightness] (where index is 0 to size-1)
def get_night_twinkle( star:int, sec:int, size:int ):
	amt = 10
	index = int((sec*0.2)*(star+1)) % size
	return index, [0, -10, amt, 0.0]

def clamp(n,a,b):
	return max(a,min(n,b))


# ----------------------------------------------------------------------------
#	RainbowHAT hardware specific
# ----------------------------------------------------------------------------
@rh.touch.A.press()
def touch_a(channel):	buttons.led_a = 1

@rh.touch.A.release()
def release_a(channel):	buttons.led_a = 0;	buttons.trigger_a = True

@rh.touch.B.press()
def touch_b(channel):	buttons.led_b = 1

@rh.touch.B.release()
def release_b(channel):	buttons.led_b = 0;	buttons.trigger_b = True

@rh.touch.C.press()
def touch_c(channel):	buttons.led_c = 1

@rh.touch.C.release()
def release_c(channel):	buttons.led_c = 0;	buttons.trigger_c = True


# ----------------------------------------------------------------------------
#	Lower level LED Display manipulation
# ----------------------------------------------------------------------------
def get_looped_range( path:list ):
	index:int = 0
	while index < len(path):
		yield path[index]
		index = index + 1
	pass

def get_display_segment_square():	
	return get_looped_range( [1,2,3,4,5,6] )

def get_display_segment_stick_jumps():
	return get_looped_range( [2,3,14,9,6,5,12,11] )

def set_display4( segment_0:int, segment_1:int, segment_2:int, segment_3:int ):
	rh.display.set_digit_raw(0, 1 << (segment_0-1))
	rh.display.set_digit_raw(1, 1 << (segment_1-1))
	rh.display.set_digit_raw(2, 1 << (segment_2-1))
	rh.display.set_digit_raw(3, 1 << (segment_3-1))


# ----------------------------------------------------------------------------
class PixelBuffer():
	def __init__(self,size,rgbi_default=[0,0,0,0]):
		self.size :int = size
		self.buffer :list = [None] * size
		for i in range(size):
			self.buffer[i] = rgbi_default
	def __len__(self):					return self.size
	def __getitem__(self, key):			return self.buffer[key]
	def __setitem__(self, key,value):	self.buffer[key] = value
	def blend(self,weight:float, target:'PixelBuffer') -> list:
		assert(self.size == target.size),"Mismatched array sizes!"
		mixed :list = []
		for i in range(self.size):		
			mixed.append([ 
				(weight * target.buffer[i][0]) + ((1-weight) * self.buffer[i][0]),
				(weight * target.buffer[i][1]) + ((1-weight) * self.buffer[i][1]),
				(weight * target.buffer[i][2]) + ((1-weight) * self.buffer[i][2]),
				(weight * target.buffer[i][3]) + ((1-weight) * self.buffer[i][3])])
		return mixed		

# ----------------------------------------------------------------------------
# Fill rainbow LEDs with colors based on offset
def set_rainbow_based_on_offset( offset:int ):
	for i in range(MAX_LEDS):	
		h =	(((i+offset)%(MAX_LEDS*2)) / (MAX_LEDS*2))
		r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(h, 1.0, 0.3)]
		rh.rainbow.set_pixel(i,r,g,b,0.5)

# ----------------------------------------------------------------------------
# Fill rainbow LEDs with colors appropriate for the time of day.
#	time, of day
#	sunrise, when a sunrise should start mixing in to morning
#	sunset, when a sunset should start mixing in to night
def set_rainbow_based_on_time( time, sunrise=6, sunset=19):
	hour 		= time.tm_hour
	minute 		= time.tm_min
	sec 		= time.tm_sec
	
	max_led 		:int  = 7							# maximum true LEDs
	size 			:int  = 12							# maximum virtual LEDs	
	pix 			:PixelBuffer = PixelBuffer(size, [0,1,0,0.05])
	night_pix 		:PixelBuffer = PixelBuffer(size, [1,0,2,0.05])	# buffer for night stars
	sunsetrise_pix	:PixelBuffer = PixelBuffer(size, [0,0,0,0.05])

	for i in range(size):
		sunsetrise_pix[i] = [5*(1+(minute%5)),0,0,0.05]

	# Start dim, slightly green (grass!)	
	pix_array_add(pix,0,1,0,0.05)
	for i in range(size):
		if i < max_led:
			shine_pixel = get_sin_shine(i,sec)
			pix[i] = [sum(n) for n in zip(*[pix[i], shine_pixel])]

	pix_array_add(night_pix,1,0,2,0.05)
	for star in range(5):
		i, pixel = get_night_twinkle(star,sec,size)
		night_pix[i] = [sum(n) for n in zip(*[night_pix[i], pixel])]

	blend_amount = 0.0
	sunsetrise_amount = 0.0
	if hour == sunrise:
		sunsetrise_amount = get_0to0_from_percent((minute / 59))
		blend_amount = ((59-minute) / 59)
	elif hour == sunset:
		sunsetrise_amount = get_0to0_from_percent((minute / 59))
		blend_amount = (minute / 59)
	elif hour < sunrise or hour > sunset:
		blend_amount = 1.0
	else:
		blend_amount = 0.0
	
	pix = pix_array_weighted_blend(pix, night_pix, blend_amount)	
	pix = pix_array_weighted_blend(pix, sunsetrise_pix, sunsetrise_amount)		
	#print("h: ",localtime.tm_hour, "  m: ", localtime.tm_min, "  blend: ",blend_amount,"   sunset: ", sunsetrise_amount)

	# "render" out to LED buffer
	for i in range(size):
		if i < max_led:
			rh.rainbow.set_pixel(i, pix[i][0], clamp(pix[i][1],0,255), clamp(pix[i][2],0,255) , clamp(pix[i][3],0,255))

# ----------------------------------------------------------------------------
# For a a given seconds (120 to 0) and a pixel index, return an RGB value for that pixel
# returns [red,green,blue] with values 0-255
def get_countdown_color( seconds:int, index:int ):	
	durration = 120
	step = int(durration / MAX_LEDS)
	active_pixel = int(seconds/step)
	if index > active_pixel:
		return [30,0,0]				# red stop
	elif index < active_pixel:
		return [2,10,2]				# green go!	
	h =	((seconds%step) / step)
	r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(h, 1.0, 0.3)]
	return [r,g,b]

# ----------------------------------------------------------------------------
# Return pixel colors for 0 and 1 respectively based on value
# returns two sets of [r,g,b]; first for off pixels, second for on pixels
def get_binary_colors( value:int ):	
	# Nice little slightly-scrambled rainbow table
	colors:list = [		
		[25,0,0],
		[15,15,0],
		[0,15,15],
		[0,0,25],
		[15,0,15],
		[20,10,0],
		[0,25,0],
		[0,10,20],
		[10,0,20],
		[20,0,10]
	]
	off_set = int(value / 128) % len(colors)
	on_set = int((value+128) / 128) % len(colors)
	return colors[off_set], colors[on_set]

# ----------------------------------------------------------------------------
# beep beep beeeeep
def play_tune():
	n_60 = [60,0.5,0.3]		# middle C
	n_64 = [64,0.5,0.3]
	n_67 = [67,0.5,0.3]
	n_72 = [72,0.5,0.3]
	n_76 = [84,0.5,0.3]
	n_79 = [84,0.5,0.3]
	n_84 = [84,0.5,0.3]
	n_60g = [60,1.0,2.0]	#lon(g) notes...
	n_64g = [64,0.8,1.2]
	n_67g = [67,0.7,0.6]
	n_72g = [72,0.6,0.6]
	pattern_a = [ n_60, n_72, n_60, n_72, n_60, n_72, n_60, n_72 ]
	pattern_b = [ n_60, n_64, n_67, n_72, n_60, n_64, n_67, n_72 ]
	pattern_c = [ n_84, n_79, n_76, n_72, n_72g, n_67g, n_64g, n_60g ]
	song = [ pattern_a, pattern_b, pattern_a, pattern_c ]
	PITCH 		:int = 0
	DURRATION 	:int = 1
	REST 		:int = 2
	for pattern in song:
		for note in pattern:
			rh.buzzer.midi_note(note[PITCH], note[DURRATION])
			time.sleep(note[REST])
			# Early out if a button is pressed
			if buttons.trigger_a or buttons.trigger_b or buttons.trigger_c:
				return

# ----------------------------------------------------------------------------
class Mode(object):
	def __init__(self, led_name:str, full_name:str=None):
		#print("Mode.__init__:",led_name)
		self.__led_name = led_name			# Name that fits in LED display
		self.__full_name =full_name			# Full name (may require scrolling)
		self.__enter_time = None			# The time when this mode entered
		self.skip_preview = True			# Does this handle the mode preview?
		self.ModeA = None
		self.ModeB = None
		self.ModeC = None
		self.FuncA = None
		self.FuncB = None
		self.FuncC = None
	
	def get_led_name(self): 		return self.__led_name
	def get_full_name(self): 		return self.__full_name
	def get_skip_preview(self): 	return self.skip_preview

	# Set the modes (can be None) that are switched to via A,B,and C buttons
	def set_abc_modes(self, mode_a=None, mode_b=None, mode_c=None):
		self.ModeA = mode_a
		self.ModeB = mode_b
		self.ModeC = mode_c

	def set_abc_funcs(self, func_a=None, func_b=None, func_c=None):
		self.FuncA = func_a
		self.FuncB = func_b
		self.FuncC = func_c

	def pre_enter(self, old_mode):
		self.__enter_time = time.monotonic()	# capture when mode started

	def enter(self, old_mode):
		pass

	# About to exit this mode, prepare properties (if any) to pass to next mode
	def exiting(self, new_mode):
		pass

	def get_properties(self):
		properties:list={}
		return properties		

	def run(self):
		print("Default run() for '" + self.get_led_name() + "' durr: " + str(self.get_durration_ms()))		

	# How long this mode has been running in milliseconds
	def get_durration_ms(self):
		return int((time.monotonic() - self.__enter_time) * 1000)


# ----------------------------------------------------------------------------
class StateMachine(object):
	def __init__(self):
		self.mode = None					# The active mode
		self.last_time = 0					# Use to determine call delta
		self.changed_mode_delay_ms = 1000	# How much time to display mode's name		
		self.force_skip_preview = False

	# Change m odes, passing any necessary information between them
	def change_mode(self, new_mode_class ):
		new_mode:Mode = new_mode_class()
		if self.mode != None:
			self.mode.exiting( new_mode )
		old_mode:Mode = self.mode
		self.mode = new_mode
		if self.mode != None:
			self.mode.pre_enter( old_mode )
			self.mode.enter( old_mode )
		self.force_skip_preview = (GetClassName(old_mode) == "MenuMode")


	# Once per frame update the mode...
	def run(self):
		if self.mode != None:
			# Unless mode handles the "preview" briefly display mode name
			isPastPreviewTime:bool = (self.mode.get_durration_ms() > self.changed_mode_delay_ms)
			if self.mode.get_skip_preview() or self.force_skip_preview or isPastPreviewTime:
				self.mode.run()
			else:
				rh.display.print_str( self.mode.get_led_name() )				
		self.last_time = time.monotonic()

	def delta(self):
		return time.monotonic() - self.last_time
	
	# Determine if any actions should be taken due to buttons.
	def evalulate_buttons(self,button_a,button_b,button_c):
		current_mode = self.mode	# capture in case a FUNC() changes the mode
		if button_a:
			if current_mode.FuncA != None: current_mode.FuncA()
			if current_mode.ModeA != None: self.change_mode( current_mode.ModeA )
		if button_b:
			if current_mode.FuncB != None: current_mode.FuncB()
			if current_mode.ModeB != None: self.change_mode( current_mode.ModeB )
		if button_c:
			if current_mode.FuncC != None: current_mode.FuncC()
			if current_mode.ModeC != None: self.change_mode( current_mode.ModeC )


# ----------------------------------------------------------------------------
#   .----..-----. .--. .-----..----.    .-.  .-.  .--.  .----..-. .-..-..-. .-..----. 
#  { {__-``-' '-'/ {} \`-' '-'} |__}    }  \/  { / {} \ | }`-'{ {_} |{ ||  \{ |} |__} 
#  .-._} }  } { /  /\  \ } {  } '__}    | {  } |/  /\  \| },-.| { } }| }| }\  {} '__} 
#  `----'   `-' `-'  `-' `-'  `----'    `-'  `-'`-'  `-'`----'`-' `-'`-'`-' `-'`----' 
state_machine = StateMachine()


# ----------------------------------------------------------------------------
# Startup sequence
# Breaks the rules a bit to play animated sequence before main loop
class StartMode(Mode):
	def __init__(self):
		Mode.__init__(self,"HELO","Hello")

	def run(self):
		print("Start: ", time.localtime(time.time()) )
		display_segment_range = get_display_segment_square()
		for segment in display_segment_range:
			set_display4(segment,segment,segment,segment)
			rh.display.show()
			time.sleep(0.08)
		display_segment_range = get_display_segment_stick_jumps()
		for segment in display_segment_range:
			set_display4(segment,segment,segment,segment)
			rh.display.show()
			time.sleep(0.08)
		state_machine.change_mode( ClockMode )

# ----------------------------------------------------------------------------
class ClockMode(Mode):
	def __init__(self):
		Mode.__init__(self,"CLOK","Clock")
		self.set_abc_modes( NapMode, MenuMode, TimeoutMode )

	def enter(self, old_mode):
		Mode.enter(self, old_mode)

	def run(self):
		global localtime
		twelvehour = (localtime.tm_hour % 12) if ((localtime.tm_hour % 12)>0) else 12
		timestr = str(twelvehour).rjust(2," ") + str(localtime.tm_min).rjust(2,"0")
		rh.display.print_str(timestr)							# set time on segemented display
		rh.display.set_decimal(1, (localtime.tm_sec %2)==0 )	# blink decimal by the second		
		set_rainbow_based_on_time( localtime )

# ----------------------------------------------------------------------------
# Like clock mode but no animation for 2 hours; then auto back to clock mode.
class NapMode(Mode):
	two_hours_ms :int = (1000*60*60*2)

	def __init__(self):
		Mode.__init__(self," NAP","Nap")
		self.set_abc_modes( ClockMode, MenuMode, None )
		self.skip_preview = False

	def enter(self, old_mode):
		rh.rainbow.set_all(0, 0, 1, 0.05)

	def run(self):
		global localtime
		twelvehour = (localtime.tm_hour % 12) if ((localtime.tm_hour % 12)>0) else 12
		timestr = str(twelvehour).rjust(2," ") + str(localtime.tm_min).rjust(2,"0")
		rh.display.print_str(timestr)							# set time on segemented display
		rh.display.set_decimal(1, (localtime.tm_sec %2)==0 )	# blink decimal by the second				
		if self.get_durration_ms() > NapMode.two_hours_ms:		# After 2 hours, change to clock
			state_machine.change_mode( ClockMode )

# ----------------------------------------------------------------------------
class TimeoutMode(Mode):
	def __init__(self):
		Mode.__init__(self,"Tout","Timeout")
		self.skip_preview = False
		self.is_tune_played :bool = False		
		self.set_abc_modes( ClockMode, ClockMode, ClockMode )

	def run(self):
		seconds:int = int(self.get_durration_ms()/1000)
		if 120-seconds > 0:
			rh.display.print_str( str(120-seconds).rjust(4," "))
		else:
			rh.display.print_str('done')			
			if self.is_tune_played == False:
				self.is_tune_played = True
				rh.display.show() 		# display immediate because tune blocks				
				play_tune()

		for i in range( MAX_LEDS ):
			rgb :list = get_countdown_color(seconds,i)
			rh.rainbow.set_pixel(6-i, rgb[0], rgb[1], rgb[2], 0.3)

# ----------------------------------------------------------------------------
class CreditsMode(Mode):
	def __init__(self):
		Mode.__init__(self,"CRDT","Credits")
		self.scroll_delay = 0
		self.scroll_delay_max = 0.25
		self.range_words = range_sub_string("    Made by tronster.com - Drink water, brush your teeth, love each other... not all at once.    ") 
		self.set_abc_modes( MenuMode, MenuMode, MenuMode )

	def enter(self, old_mode):
		Mode.enter(self,old_mode)
		rh.display.set_decimal(1, False)

	def run(self):
		if self.scroll_delay <= 0:
			self.scroll_delay = self.scroll_delay_max
			word = next(self.range_words)
			rh.display.print_str(word)
		else:
			self.scroll_delay = self.scroll_delay - state_machine.delta()
		set_rainbow_based_on_offset( int(self.get_durration_ms()/250) )

# ----------------------------------------------------------------------------
# Count upwards on LED display and show binary representation above it on the
# RGB leds. LEDs will use different colors for 0 and 1 for every 128 count.
class CountMode(Mode):
	def __init__(self, led_name:str, full_name:str):
		Mode.__init__(self,led_name,full_name)
		self.num = -1
		self.update_delay = 0
		self.update_delay_max = 1.0		# update once a second
		self.set_abc_modes(PauseMode, MenuMode, PauseMode)				

	def get_properties(self):
		num = self.num
		return {"num" : num}

	def enter(self, old_mode):
		if GetClassName(old_mode) == "PauseMode":		
			self.num = old_mode.get_properties()["num"]
			self.skip_preview = True
		else:
			self.num = -1
			self.skip_preview = False
		self.update_delay = 0
		# Since rainbow hardware (or driver) has issue with clearing display here
		# work around by always outputing spaces in run() before the number.

	def run(self):
		# Only update display every second
		if self.update_delay > 0:
			self.update_delay = self.update_delay - state_machine.delta()
			return False
		self.update_delay = self.update_delay + self.update_delay_max
		self.num = self.num + 1

		# Show binary LEDs based on string of 0 & 1s, with 0 padding & reverse w/ least significant digit first.
		binary = f'{self.num:07b}'[::-1]
		off_color, on_color = get_binary_colors(self.num)
		for index,c in enumerate(binary, 0):
			if c=="1":
				rh.rainbow.set_pixel(index, on_color[0], on_color[1], on_color[2], 0.4)				
			else:
				rh.rainbow.set_pixel(index, off_color[0], off_color[1], off_color[2], 0.1)
			index = index + 1
			if index>=7:
				break
		return True

# ----------------------------------------------------------------------------
class CountDecimalMode(CountMode):
	def __init__(self):
		super().__init__("1234","Count Decimal")

	def run(self):
		if super().run():
			rh.display.print_str( str(self.num).rjust(4," ") )

# ----------------------------------------------------------------------------
class CountHexMode(CountMode):
	def __init__(self):
		super().__init__(" HEX","Count Hexadecimal")

	def run(self):
		if super().run():
			rh.display.print_str( hex(self.num)[2:].upper().rjust(4," ") )

# ----------------------------------------------------------------------------
# Pause an existing mode, passes back any properties that were set.
class PauseMode(Mode):
	def __init__(self):
		Mode.__init__(self,"PAUS","Pause")
		self.__properties :list = {}
		self.__blink_value:str = "    "

	def get_properties(self):
		return self.__properties

	def enter(self, old_mode):
		Mode.enter(self, old_mode)
		self.__properties = old_mode.get_properties()
		if self.__properties["num"] != None:
			self.__blink_value = str(self.__properties["num"]).rjust(4," ") 
		old_mode_class = old_mode.__class__
		self.set_abc_modes( old_mode_class, old_mode_class, old_mode_class )

	def run(self):
		if (int(self.get_durration_ms() / 1000) % 2) == 0:
			rh.display.print_str( self.__blink_value )
		else:
			rh.display.print_str( self.get_led_name() )

# ----------------------------------------------------------------------------
#
class TempatureMode(Mode):
	def __init__(self):
		Mode.__init__(self,"TEMP","Tempature")
		self.is_fahrenheit = True
		self.set_abc_funcs(None, None, self.change_tempature_scale )
		self.set_abc_modes(None, MenuMode, None )

	def run(self):
		temp = rh.weather.temperature()
		if self.is_fahrenheit:
			temp = (temp * (9/5)) + 32
		rh.display.print_float( temp )

	def change_tempature_scale(self):
		self.is_fahrenheit = not self.is_fahrenheit

# ----------------------------------------------------------------------------
class MenuMode(Mode):
	modes		:list = [TempatureMode,CountDecimalMode,CountHexMode,ClockMode,NapMode,TimeoutMode,CreditsMode]
	mode_index	:int = 0
	last_index	:int = 0

	def __init__(self):
		Mode.__init__(self,"MENU","Menu")	
		self.set_abc_funcs(self.func_a, self.func_b, self.func_c)

	def enter(self, old_mode):
		Mode.enter(self, old_mode)
		rh.rainbow.set_all(1, 0, 1, 0.1)

	def run(self):
		preview_mode = self.modes[MenuMode.mode_index]()				
		rh.display.print_str( preview_mode.get_led_name() )
		brightness = 0.3 + ( 0.2 * float(int(self.get_durration_ms()/1000) % 2))
		rh.rainbow.set_pixel((MAX_LEDS-1) - self.last_index, 1, 0, 1, 0.1 )
		rh.rainbow.set_pixel((MAX_LEDS-1) - MenuMode.mode_index, 30, 30, 0, brightness )

	# Change to selected mode
	def func_a(self):
		print("down: ",(MenuMode.mode_index - 1) % len(self.modes))
		self.last_index = MenuMode.mode_index
		MenuMode.mode_index = (MenuMode.mode_index - 1) % len(self.modes)

	# Move down a mode in the menu
	def func_b(self):
		buttons.lower_triggers()	# kluge: otherwise may go through to another state
		selected_class = self.modes[MenuMode.mode_index]
		selected_mode = selected_class()
		print("Selected Mode: ", selected_mode.get_led_name())
		state_machine.change_mode( selected_class )

	# Move up a mode in the menu
	def func_c(self):
		print("  up: ",(MenuMode.mode_index + 1) % len(self.modes))
		self.last_index = MenuMode.mode_index
		MenuMode.mode_index = (MenuMode.mode_index + 1) % len(self.modes)


# ----------------------------------------------------------------------------
# Main
# Using exception so ctrl-c will cleanly break out.
try:
	random.seed()
	state_machine.change_mode( StartMode )
	while isRunning:
		localtime = time.localtime(time.time())
		state_machine.evalulate_buttons(buttons.trigger_a, buttons.trigger_b, buttons.trigger_c)
		buttons.lower_triggers()
		state_machine.run()
		rh.lights.rgb(buttons.led_a, buttons.led_b, buttons.led_c)
		rh.display.show()
		rh.rainbow.show()		
		time.sleep(0.01)
except KeyboardInterrupt:
	pass
