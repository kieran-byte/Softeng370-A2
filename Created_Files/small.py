#!/usr/bin/env python
from __future__ import print_function, absolute_import, division
import logging
from collections import defaultdict
from errno import ENOENT
from stat import S_IFDIR, S_IFLNK, S_IFREG
from time import time
import unicodedata
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
import disktools
import os

if not hasattr(__builtins__, 'bytes'):
    bytes = str

#Author:
#Kieran Bettesworth
#kbet075
#340071034

#unused blocks is block zero
#master table is block one


class Memory(LoggingMixIn, Operations):
    'Example memory filesystem. Supports only one level of files.'

    def __init__(self):
        self.files = {}
        self.metafiles = []
        self.data = defaultdict(bytes)
        self.fd = 0
        #determines the freeblocks
        self.determine_free_blocks()
        #reads in the master table which will be needed to recreate stored items
        self.read_master_table()
        now = time()
        self.files['/'] = dict(
            st_mode=(S_IFDIR | 0o755),
            st_ctime=now,
            st_mtime=now,
            st_atime=now,
            st_nlink=2)

    def chmod(self, path, mode):
        self.files[path]['st_mode'] &= 0o770000
        self.files[path]['st_mode'] |= mode
        return 0

    def chown(self, path, uid, gid):
        self.files[path]['st_uid'] = uid
        self.files[path]['st_gid'] = gid

    def create(self, path, mode):
        #need to add support for when multiple files are made at once

        now = int(time())
        self.files[path] = dict(
            st_mode=(S_IFREG | mode),
            st_nlink=1,
            st_size=0,
            st_ctime=now,
            st_mtime=now,
            st_block = "",
            st_atime=now)

        self.fd += 1
        # now we need to append the data block responsible for meta data
        selectedblock = self.freeBlocks.pop()

        #cahnges the ownership of the file to the current user and group
        self.chown(str(path), os.getuid(), os.getgid())

        #reads in master table
        mastertable = disktools.read_block(1)
        mastertable = mastertable.replace("\x00", "")

        #builds the meta line for storage, adding a colon to differentiate each item
        mastertable = mastertable + ":"
        mastertable = mastertable + str(path) + "," + str(selectedblock)

        #creates and appends the latest addition to the metafiles
        storestring = ":" + str(path) + "," + str(selectedblock)
        self.metafiles.append(storestring)

        #resets the data then writes the new data into the master storage table
        disktools.write_block(1, 64 * "\x00")
        disktools.write_block(1, mastertable)

        #calls a function that will store all meta data of the storage block
        self.store_meta_data(int(selectedblock), path)

        #Creates a string of all blocks that are free
        freeblocks = "Data blocks not in use:"
        for block in self.freeBlocks:
            freeblocks = freeblocks + block
            freeblocks = freeblocks + ","

        #to remove final comma
        freeblocks = freeblocks[:-1]

        #writes null bytes to the block then overwrites with the new empty files
        disktools.write_block(0, 64 * "\x00")
        disktools.write_block(0, freeblocks)

        #returns from the function
        return self.fd

    def store_meta_data(self, selectedblock, path):
        #this function needs to store the meta data of a file in the selected block

        # gets the free block for data storage
        datablock = self.freeBlocks.pop()
        self.files[path]["st_block"] = datablock

        #collects all the meta daa of the object
        #writestring = str(self.files[path])
        writestring = str(self.files[path].get("st_ctime")) + "," + str(self.files[path].get("st_mtime")) + "," + str(self.files[path].get("st_size")) + ","
        writestring = writestring + str(self.files[path].get("st_atime")) + "," + str(self.files[path].get("st_mode")) + "," + str(self.files[path].get("st_nlink")) + ","
        writestring = writestring + str(self.files[path].get("st_size")) + "," + str(self.files[path].get("st_block"))
        writestring = writestring + "," + str(self.files[path].get("st_uid")) + "," + str(self.files[path].get("st_gid"))


        #determines the remaning free blocks
        freeblocks = "Data blocks not in use:"
        for block in self.freeBlocks:
            freeblocks = freeblocks + block
            freeblocks = freeblocks + ","

        #removes final comma, purges data and rewrites the remaning freeblock
        freeblocks = freeblocks[:-1]
        disktools.write_block(0, 64 * "\x00")
        disktools.write_block(0, freeblocks)

        #writes the meta data to the slected data bock that has been allocated for its storage
        disktools.write_block(selectedblock, writestring)

    #returns the dictionary of the selected file path if it exists
    def getattr(self, path, fh=None):

        #this error triggers for some reason which implies that path might not be in there
        if path not in self.files:
            raise FuseOSError(ENOENT)

        return self.files[path]

    def getxattr(self, path, name, position=0):
        attrs = self.files[path].get('attrs', {})

        try:
            return attrs[name]
        except KeyError:
            return ''       # Should return ENOATTR

    def listxattr(self, path):
        attrs = self.files[path].get('attrs', {})
        return attrs.keys()

    def mkdir(self, path, mode):
        print("TOUCH USED")
        self.files[path] = dict(
            st_mode=(S_IFDIR | mode),
            st_nlink=2,
            st_size=0,
            st_ctime=time(),
            st_mtime=time(),
            st_atime=time())

        self.files['/']['st_nlink'] += 1

    def open(self, path, flags):
        #fd appears to be some kind of counter, im not sure how its used but it appears to
        #be involved in the fuse file, not in the small.py file, therefore no cahnges to stored data need to occur
        self.fd += 1
        return self.fd

    def read(self, path, size, offset, fh):
        return self.data[path][offset:offset + size]

    def readdir(self, path, fh):
        return ['.', '..'] + [x[1:] for x in self.files if x != '/']

    def readlink(self, path):
        return self.data[path]

    def removexattr(self, path, name):
        attrs = self.files[path].get('attrs', {})

        try:
            del attrs[name]
        except KeyError:
            pass        # Should return ENOATTR

    def rename(self, old, new):
        self.data[new] = self.data.pop(old)
        self.files[new] = self.files.pop(old)

    def determine_free_blocks(self):
        self.freeBlocks = []
        #reads in the blockstring then splits if taking only after the :, then splits it after every comma
        blockString = disktools.read_block(0)
        blockString = blockString.split(":", 1)[1]
        #removes the rest of the null values off the list
        blockString = blockString.split("\x00", 1)[0]
        self.freeBlocks = blockString.split(",")

    def read_master_table(self):
        storageblocks = str(disktools.read_block(0)).replace("\x00", "")
        storageblock = storageblocks.split(":", 1)[1]

        # splits the block every comma so the block count can be done
        blocklist = []
        blocklist = storageblock.split(",")

        # the last item has null bytes on it which cant be removed before changing to a list for some reason so this is here
        count = 0
        for item in blocklist:
            blocklist.remove(item)
            item = item.replace("\x00", "")
            blocklist.insert(count, item)
            count = count + 1

        # there should be 14 items in the list if none are being used at the time
        if len(blocklist) != 14:
            # needs to read in master table first to find meta data lines
            masterlist = str(disktools.read_block(1)).split(":")

            # then items are added to the self.metafiles
            for item in masterlist:
                if str(item) != ":" and str(item) != "":
                    item = item.replace("\x00", "")
                    self.metafiles.append(item)

            # now we get all the data stored in the meta files
            for metaline in self.metafiles:

                # gets the loaction of stored meta data and path of current meta data item
                metaline = str(metaline).replace("\x00", "")

                datalocation = int(str(metaline).split(",", 1)[1])
                path = str(metaline).split(",", 1)[0]
                metadata = disktools.read_block(datalocation)

                metadata = str(metadata).replace(" ", "")
                metaitems = metadata.split(",")



                # null bytes must also be removed here
                metaitems[-1] = metaitems[-1].replace("\x00", "")

                # creates the dictionary for the path and adds in all the meta data
                self.files[path] = dict(
                    st_mode=int(metaitems[4]),
                    st_nlink=int(metaitems[5]),
                    st_size=int(metaitems[2]),
                    st_ctime=int(metaitems[0]),
                    st_mtime=int(metaitems[1]),
                    st_block=str(metaitems[7]),
                    st_atime=int(metaitems[3]),
                    st_uid=int(metaitems[8]),
                    st_gid=int(metaitems[9]))

                #all meta data is loaded in, now regular data needs to be loaded in
            #for item in self.metafiles:

                path = str(metaline).split(",", 1)[0]
                metalocation = int(str(metaline).split(",", 1)[1])
                storagelocation = disktools.read_block(int(metalocation))
                storagelocation = str(storagelocation).rsplit(",", 2)[0]
                storagelocation = storagelocation.rsplit(",", 1)[1]
                storagelocation =  int(storagelocation)

                if self.files[path]["st_size"] > 56:
                        #grabs the second file and reads in from that as well
                        #location is stored in meta data, then near the end of that will be the location of the second storage block
                    storedcontents = disktools.read_block(int(storagelocation))
                    storedcontents = str(storedcontents)[-8]

                        #concatenates both files into one string
                    self.data[path] = str(disktools.read_block(storagelocation)) + str(disktools.read_block(int(storedcontents)))

                else:
                    #reads in data simply
                    self.data[path] = disktools.read_block(int(storagelocation))


                #then the file is created and the data written to it
                filename = path.replace("/", "")
                directory = str(os.getcwd()) + str(filename)
                f = open(directory, "w+")
                f.write(self.data[path])
                f.close()

    def rmdir(self, path):
        # with multiple level support, need to raise ENOTEMPTY if contains any files
        self.files.pop(path)
        self.files['/']['st_nlink'] -= 1

    def setxattr(self, path, name, value, options, position=0):
        # Ignore options
        attrs = self.files[path].setdefault('attrs', {})
        attrs[name] = value

    def statfs(self, path):
        return dict(f_bsize=512, f_blocks=4096, f_bavail=2048)

    def symlink(self, target, source):
        self.files[target] = dict(
            st_mode=(S_IFLNK | 0o777),
            st_nlink=1,
            st_size=len(source))

        self.data[target] = source

    def truncate(self, path, length, fh=None):
        # make sure extending the file fills in zero bytes
        self.data[path] = self.data[path][:length].ljust(
            length, '\x00'.encode('ascii'))
        #modifies the size variable stored in the file path to the size of the data stored
        #on testing this function writes the size of "hello world" to be zero
        #while write counts it to be 12 bytes so only the write function will change the file size
        self.files[path]['st_size'] = length

    #even though the remove command works, some part of the program is still holding the file
    #therefore the file is still visible despite being unlinked. This file cannot be accessed but is displayed on ls
    #upon further testing with memory.py
    #the logging.info calls seem to trap the file in the program which means it cant be completely removed?
    def unlink(self, path):

        # first we find the location of the meta data storage
        file = ""
        for item in self.metafiles:
            if str(path) in item:
                file = item
                break

        removefile = file

        # remove any thing thats not part of the file data location
        file = file.split(",", 1)[1]
        file = file.replace(" ", "")

        #file is where the meta data is stored
        blocks = []
        blocks = self.files[path].get("st_block").split(" ", 2)[:]

        #clears blocks used for data
        disktools.write_block(int(blocks[0]), 64 * "\x00")
        if len(blocks) > 1:
            disktools.write_block(int(blocks[1]), 64 * "\x00")

        #clears blocks used for meta data
        disktools.write_block(int(file), 64 * "\x00")

        #appends the two data blocks that must be there and checks the second one, if a number its added
        self.freeBlocks.append(blocks[0])
        self.freeBlocks.append((int(file)))
        if len(blocks) > 1:
            self.freeBlocks.append(blocks[1])

        #then the new free blocks are rewritten to the storage drive
        freeblocks = "Data blocks not in use:"
        for block in self.freeBlocks:
                freeblocks = freeblocks + str(block)
                freeblocks = freeblocks + ","

        # and writes the remaning free blocks back onto the storage drive
        freeblocks = freeblocks[:-1]
        disktools.write_block(0, 64 * "\x00")
        disktools.write_block(0, freeblocks)

        writestring = ""
        for metafile in self.metafiles:
            writestring = writestring + str(metafile)

        disktools.write_block(1, 64 * "\x00")
        disktools.write_block(1, writestring)

        #can now remove files that have no data
        item = self.data.get(path)
        if str(item) in self.data:
            self.data.pop(path)

    #this may need cahnges to update the file times, I am not sure
    def utimens(self, path, times=None):
        now = time()
        atime, mtime = times if times else (now, now)
        #modifies the time stored in the file
        self.files[path]['st_atime'] = atime
        self.files[path]['st_mtime'] = mtime

        #this needs to be reflected in the file storage of the file

    def write(self, path, data, offset, fh):
        #gets the current time then updates the a,c and m time of the file in the program
        timenow = int(time())
        self.files[path]['st_atime'] = timenow
        self.files[path]['st_mtime'] = timenow
        self.files[path]['st_ctime'] = timenow

        stringdata = str(data).replace("\x00", "")

        self.data[path] = (
            # make sure the data gets inserted at the right offset
            self.data[path][:offset].ljust(offset, '\x00'.encode('ascii'))
            + stringdata
            # and only overwrites the bytes that data is replacing
            + self.data[path][offset + len(stringdata):])
        self.files[path]['st_size'] = len(self.data[path])

        #gets the new up to date meta data of the file
        output = ()
        output = self.files[path]

        #writes the null bytes then writes the new data to the meta storage block
        writestring = str(self.files[path].get("st_ctime")) + "," + str(self.files[path].get("st_mtime")) + "," + str(self.files[path].get("st_size")) + ","
        writestring = writestring + str(self.files[path].get("st_atime")) + "," + str(self.files[path].get("st_mode")) + "," + str(self.files[path].get("st_nlink")) + ","
        writestring = writestring + str(self.files[path].get("st_size")) + "," + str(self.files[path].get("st_block"))
        writestring = writestring + "," + str(self.files[path].get("st_uid")) + "," + str(self.files[path].get("st_gid"))

        #first we find the location of the meta data storage
        file = ""
        for item in self.metafiles:
            if str(path) in item:
                file = item
                break

        #remove any thing thats not part of the file data location
        file = file.split(",", 1)[1]
        file = file.replace(" ", "")

        #writes all nulls then the data into the meta data location, this completes the meta data update
        disktools.write_block(int(file), 64 * "\x00")
        disktools.write_block(int(file), writestring)

        blocks = []
        # blocks[0] = self.files[path]
        blocks = self.files[path].get("st_block").split(" ", 2)[:]

        # needs to check if there is a block stored in the final few bits
        # needs to check if the data is over 64 bytes
        filesize = str(self.files[path].get("st_size")).replace("\x00", "")
        filesize = filesize.replace(" ", "")

        if (int(filesize) > 56):

            #now we need to split the data into two parts
            n = 56
            split_string = [self.data[path][i:i + n] for i in range(0, len(self.data[path]), n)]
            if len(split_string) > 2:
                raise IOError("File size is not currently supported")

            #gets all the blocks that the data is stored in
            blocklist = str(self.files[path].get("st_block"))
            blocklist = blocklist.replace("bytearray", "")

            #blocks = blocks + int(self.files[path].get("st_block").split("",1)[1])

            #check how many data blocks were assigned before
            if int(len(blocks)) == 1:
                #This for when the file started with lesser then 56 bytes and is now being updated to have over 56
                #having this always over 56 bytes having a new location means that read in is substasially easier
                # gets a new free block and determines the remaining free block
                datablock = self.freeBlocks.pop()
                freeblocks = "Data blocks not in use:"
                for block in self.freeBlocks:
                    freeblocks = freeblocks + str(block)
                    freeblocks = freeblocks + ","

                # and writes the remaning free blocks back onto the storage drive
                freeblocks = freeblocks[:-1]
                disktools.write_block(0, 64 * "\x00")
                disktools.write_block(0, freeblocks)

                # adds the new data block to the file list
                self.files[path]["st_block"] = self.files[path]["st_block"] + " " + str(datablock)

                #we need to clear the original block as well as the second one, just in case
                disktools.write_block(int(blocks[0]), 64 * "\x00")
                disktools.write_block(int(datablock), 64 * "\x00")

                #we write the first 56 bytes into the first one as well as the second block number
                disktools.write_block(int(blocks[0]), split_string[0] + str(datablock))
                disktools.write_block(int(datablock), split_string[1])


            elif (int(len(blocks)) == 2):
                #file started with two storage blocks given which means we dont need to assign another, the rest is the same

                # we need to clear the original block as well as the second one, just in case
                disktools.write_block(int(blocks[0]), 64 * "\x00")
                disktools.write_block(int(blocks[1]), 64 * "\x00")

                # we write the first 56 bytes into the first one as well as the second block number
                disktools.write_block(int(blocks[0]), split_string[0] + str(blocks[1]))
                disktools.write_block(int(blocks[1]), split_string[1])

        else:
            #if all the data can fit then null is written in and then the data is overwritten

            #there is a chance that there were two data blocks and we are now transitining to one block
            if (int(len(blocks)) == 2):

                #second block needs to be freed

                #changes the listed blocks to be the first one
                self.files[path]["st_block"] = str(blocks[0])
                disktools.write_block(int(self.files[path].get("st_block")), 64 * "\x00")

                #clears the block no longer in use, then added back to the free blocks
                disktools.write_block(int(blocks[1]), 64 * "\x00")
                self.freeBlocks.append(int(blocks[1]))

                #then the new free blocks are rewritten to the storage drive
                freeblocks = "Data blocks not in use:"
                for block in self.freeBlocks:
                    freeblocks = freeblocks + str(block)
                    freeblocks = freeblocks + ","

                # and writes the remaning free blocks back onto the storage drive
                freeblocks = freeblocks[:-1]
                disktools.write_block(0, 64 * "\x00")
                disktools.write_block(0, freeblocks)

                #then rest of data is wrtitten to the drive normally
                disktools.write_block(int(self.files[path].get("st_block")), 64 * "\x00")
                disktools.write_block(int(self.files[path].get("st_block")), self.data[path])

            elif (int(len(blocks)) == 1):
                #then proceed normally

                disktools.write_block(int(self.files[path].get("st_block")), 64 * "\x00")
                disktools.write_block(int(self.files[path].get("st_block")), self.data[path])

        return len(data)


if __name__ == '__main__':
    import argparse


    parser = argparse.ArgumentParser()
    parser.add_argument('mount')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)

    # changes what the logging.info outputs
    #logging.basicConfig(level=logging.INFO)
    fuse = FUSE(Memory(), args.mount, foreground=True)
