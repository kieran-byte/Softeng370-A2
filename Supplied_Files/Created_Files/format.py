#!/usr/bin/env python
import disktools

#Author:
#Kieran Bettesworth
#kbet075
#340071034

#blocks 0 and 1 are system reserved
#blocks are assumed to be empty so no null bytes are written to them
disktools.write_block(0, "Data blocks not in use:2,3,4,5,6,7,8,9,10,11,12,13,14,15")
