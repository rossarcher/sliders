import sys
import numpy as np

class VecToLso:
    def __init__(self, vec_script_fpath,
                 options={'loop': True, 'dark after': False, 'smooth': True}):
        # File path information
        self.src = vec_script_fpath  # File path and name of the .LSS file
        self.dst = vec_script_fpath.replace('.vec', '.lso')
        # Solution vectors from solver
        self.solution_vectors = []  # The solutions in frame order.  
        # Compiler results
        self.compile_errors = 0  # No errors yet
        self.frame_error_list = []  # List of frame numbers which encountered errors
        self.num_channels = 8  # Initial assumption is Octa.  Overwritten at solution success

        # Cope with the options:
        # 'smooth' = smooth between frames (if False, transitions between frames are abrupt)
        # 'loop' = at the end of the frame, start over at the beginning)
        # 'dark after' = at the end of the script, go dark.  Else play the last frame "forever".
        #     Note that if 'loop' is True, then 'dark after' is ignored, as there is
        #     effectively never a last frame to play
        # The default options, is to use a standard palette match,
        # smooth between frames and repeat the script in a loop, for backward compatibility reasons.
        # and because there have to be some kind of default settings.

        self.smooth = options['smooth']
        self.loop = options['loop']
        self.dark_after = False
        if not self.loop:
            # Dark after option is only significant if script does not repeat forever
            self.dark_after = options['dark after']

        # An empty script still has the mandatory 512 byte header
        # self.script_length = HEADER_SIZE
        # Keep track of where the next frame data is going into target script
        # self.script_pc = HEADER_SIZE
        self.read_vec(vec_script_fpath)
        self.generate_lso_from_lss(self.dst)
        return

    def read_vec(self, fpath):
        try:
            fh = open(fpath, 'r')
        except:
            print('Unable to locate or open %s' % fpath)
            sys.exit(-1)
        vecstr = fh.readlines()

        self.solution_vectors = []
        
        for sl in vecstr:
            sum = 0.0
            if len(sl) > 8:
                slv = sl.split(',')
                sum = 0.0
                nxt = []
                for i in range(len(slv)):
                    slve = slv[i]
                    if (i > 0):
                        sum += float(slve)
                    nxt.append(float(slve)) 

                self.solution_vectors.append(nxt)
            avg = sum/8.0
            if (avg > 0.3):
                print('Drive level %s is too high! Aborting' % str(nxt))
                sys.exit(-1)
        return


    def generate_lso_from_lss(self, lso_filepath):
        SCRIPT_HEADER_SIZE = 512
        FRAME_DATA_BEGINS = SCRIPT_HEADER_SIZE
        OFFSET_SCRIPT_SIZE = 0
        OFFSET_FRAME_DATA_END = 4
        OFFSET_SIGNATURE = 8
        OFFSET_NUM_CHANNELS = 16
        OFFSET_BYTES_PER_CHANNEL = 17
        OFFSET_DONT_REPEAT_FLAG = 18
        OFFSET_TAG = 19
        OFFSET_SMOOTHING = 24
        FRAME_SIZE_OCTA = 32
        OCTA_CHANNELS = 8
        self.header_size = SCRIPT_HEADER_SIZE  # Header size is 512 bytes for every kind of luminaire up to date (9/1/18)
        # Determine the num
        if not (len(self.solution_vectors[0])-1) == OCTA_CHANNELS:
            print('Invalid input vector file. Each entry must be 9 values: milliseconds, then 8 values from 0.0 to 1.0')
            sys.exit(-1)

        # The first 16 bytes has 4 bytes for repeat count and 2 for subroutine, leaving room for 5 two byte channels
        self.frame_size = FRAME_SIZE_OCTA  # Octa (8 channel 16 bit PWM) frames are 32 bytes each (8 channels)
        self.nchans = OCTA_CHANNELS
        self.nframes = len(self.solution_vectors)
        self.script_len = self.header_size + (self.nframes * self.frame_size)
        self.script = np.zeros(self.script_len, dtype=np.uint8)
        baseaddr = self.header_size

        print('\n****************************************************************\n')
        for fnum in range(0, self.nframes):
            dur = int(self.solution_vectors[fnum][0])
            vec = self.solution_vectors[fnum][1:]
            print('Frame#%d: duration(mS)=%d drive_vector=%s' % (fnum, dur, str(vec)))
            for chan in range(0, self.nchans):
                try:
                    drv = int (vec[chan] * 65535.0)
                except:
                    drv = int(0)

                if (chan < 5):
                    self.script[2 * chan + baseaddr] =  drv & 0xFF
                    self.script[2 * chan + baseaddr + 1] = (drv >> 8) & 0xFF
                else:
                    self.script[2 * chan + baseaddr + 6] = drv & 0xFF
                    self.script[2* chan + baseaddr + 7] = (drv >> 8) & 0xFF
            
            self.script[baseaddr + 10] = 0  # Script VM subroutine calls would go here. $0000=no call
            self.script[baseaddr + 11] = 0  # For now, script subroutine calls are disabled
            # Now write out the repeat count
            self.script[baseaddr + 12] = dur & 0xFF
            self.script[baseaddr + 13] = (dur >> 8) & 0xFF
            self.script[baseaddr + 14] = (dur >> 16) & 0xFF
            self.script[baseaddr + 15] = (dur >> 24) & 0xFF
            baseaddr += self.frame_size
            

        self.script[OFFSET_SCRIPT_SIZE + 0] = self.script_len & 0xFF
        self.script[OFFSET_SCRIPT_SIZE + 1] = (self.script_len >> 8) & 0xFF
        self.script[OFFSET_SCRIPT_SIZE + 2] = (self.script_len >> 16) & 0xFF
        self.script[OFFSET_SCRIPT_SIZE + 3] = (self.script_len >> 24) & 0xFF

        self.script[OFFSET_FRAME_DATA_END + 0] = self.script_len & 0xFF
        self.script[OFFSET_FRAME_DATA_END + 1] = (self.script_len >> 8) & 0xFF
        self.script[OFFSET_FRAME_DATA_END + 2] = (self.script_len >> 16) & 0xFF
        self.script[OFFSET_FRAME_DATA_END + 3] = (self.script_len >> 24) & 0xFF

        self.script[OFFSET_SIGNATURE + 0] = 0x02
        self.script[OFFSET_SIGNATURE + 1] = 0x18
        self.script[OFFSET_SIGNATURE + 2] = 0x02
        self.script[OFFSET_SIGNATURE + 3] = 0x65

        self.script[OFFSET_NUM_CHANNELS] = self.nchans
        self.script[OFFSET_BYTES_PER_CHANNEL] = 2

        if (self.loop == False):
            self.script[OFFSET_DONT_REPEAT_FLAG] = 0x01
        self.script[OFFSET_TAG] = 0x01

        if (self.smooth == True):
            self.script[OFFSET_SMOOTHING] = 0x01
        # Write the binary image to the target file
        self.script.tofile(self.dst)
    
        return

if (len(sys.argv) != 2):
    print("Incorrect use.  Use python sliders.py <name of input vector file>")
    sys.exit(-1)


lsogen = VecToLso(sys.argv[1])
sys.exit(0)
