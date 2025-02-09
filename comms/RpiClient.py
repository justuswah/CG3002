import serial
import time
import socket
import sys
import threading
import time
import CircularBuffer
import random
import operator
import csv

from Crypto.Cipher import AES
from Crypto import Random
from Crypto.Util.py3compat import *

import base64
import numpy as np
import math

#global variables
mutex = threading.Lock()

voltage = 0
current = 0
power = 0
cum_power = 0


class ReceiveData(threading.Thread):
        def __init__(self, buffer, port, period, packetSize):
                threading.Thread.__init__(self)
                self.buffer = buffer
                self.port = port
                self.period = period
                self.packetSize = packetSize

        def run(self):
                self.readData()

         # Read data from arduino
         # Packet format: Packet ID, x1, y1, z1, x2, y2, z2, x3, y3, z3,
         # voltage, current, power, cumpower, checksum
        def readData(self):
                nextTime = time.time() + self.period
                if not self.buffer.isFull():
                        rcv = self.port.read(self.packetSize)
                        mutex.acquire()
                        self.buffer.put(rcv)
                        mutex.release()
                threading.Timer(nextTime - time.time(), self.readData).start()               

class storeData(threading.Thread):
        def __init__(self, buffer, port, powerList, current_move, client):
                threading.Thread.__init__(self)
                self.buffer = buffer
                self.port = port
                self.powerList = powerList
                self.current_move = current_move
                self.actions = ['idle', 'handmotor', 'bunny', 'tapshoulder', 'rocket', 'cowboy', 'hunchback', 'jamesbond','chicken', 'movingsalute', 'whip', 'logout']
                self.machine_learning_data_set = []
                self.client = client

        def run(self):
                self.storeData()
                
        def run_machine_learning(self):
                #dalson, leonard, can use this function. data (2d array) is in self.machine_learning_data_set
                predicted_action = self.actions[0] #use idle for testing
            
                #once machine learning code is done, this function will send data
                self.client.run(predicted_action)
        
        def storeData(self):
                mutex.acquire()
                dataList = self.buffer.get()
                mutex.release()

                if dataList: #list not empty
                        for data in dataList:
       
                            check_sum = data.rsplit(",",1)[1].rstrip('\x00')
                            
                            data = data.rsplit(",",1)[0]
                            
                            test_sum = reduce(operator.xor, [ord(c) for c in data])
                            
                            ack = False
                            if True:
                            #if test_sum == int(check_sum.rstrip('\0')):
                                    ack = True
                                    #print("checksum success")
                                    mutex.acquire()
                                    
                                    data = [x.rstrip('\x00') for x in data.split(',')]
                                    
                                    self.powerList[0] = data[13]
                                    self.powerList[1] = data[14]
                                    self.powerList[2] = data[15]
                                    self.powerList[3] = data[16]
                                    
                                    self.nextID = (int(data[0]) + 1)%self.buffer.getSize()
                                    mutex.release()
                                    
                                    #storing into csv
                                    with open('/home/pi/Desktop/data.csv', 'a') as csvfile:
                                        filewriter = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_NONE)
                                        filewriter.writerow(data)
                                    
                                    #storing into array
                                    self.machine_learning_data_set.append(data)
                                        
                                    
                            else:
                                    ack = False                        #some samples has problem
                                    print('checksum failed')
                                    break

                        if ack:
                                #print("sending ack")
                                self.port.write('A')
                                self.port.write(chr(self.nextID))
                                mutex.acquire()
                                self.buffer.ack(self.nextID)
                                mutex.release()
                        else:
                            #print("no ack")
                            self.port.write('N')
                            self.port.write(chr(self.nextID))
                            mutex.acquire()
                            self.buffer.nack(self.nextID)
                            mutex.release()
                            
                        if len(self.machine_learning_data_set) > 150:
                            self.run_machine_learning()
                            self.machine_learning_data_set = []
 
                threading.Timer(0.06, self.storeData).start()

        
class clientComms(threading.Thread):
        def __init__(self, powerList, current_move):
                threading.Thread.__init__(self)
                self.socket = []
                self.SECRET_KEY = "panickerpanicker"
                self.actions = ['idle', 'handmotor', 'bunny', 'tapshoulder', 'rocket', 'cowboy', 'hunchback', 'jamesbond','chicken', 'movingsalute', 'whip', 'logout']
                self.powerList = powerList
                self.moveIndex = 0
                self.current_move = current_move
                
                try:
                        self.setUpComms()
                        self.connectToServer(self.socket[0], self.socket[1])
                        
                        time.sleep(3)
                        self.connectToServer(self.socket[0], self.socket[1])
                
                except KeyboardInterrupt:
                        sys.exit(1)

        def run(self, action):
                        
            iv = Random.new().read(AES.block_size)
            cipher = AES.new(self.SECRET_KEY, AES.MODE_CBC, iv)
            mutex.acquire()
            message = ("#" + action+ "|"+str(self.powerList[0]) + "|" + str(self.powerList[1]) + "|" + str(self.powerList[2]) + "|" + str(self.powerList[3]) + "|").encode('utf8').strip()                             
            print("sent message: "+message)
            paddedMessage = self.padMessage(message, AES.block_size)
            encryptedMessage = cipher.encrypt(paddedMessage)
            encodedMessage = base64.b64encode(iv + encryptedMessage)
            time.sleep(3)
            
            #writing csv file, can delete
            with open('/home/pi/Desktop/data.csv', 'a') as csvfile:
                                        filewriter = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_NONE)
                                        filewriter.writerow(action)
          

            self.sendMessage(encodedMessage)
            mutex.release() #change this to be input

        def setUpComms(self):
                self.socket.append(sys.argv[1])
                self.socket.append(sys.argv[2])

        def connectToServer(self, host, port):
                print("attempting to connect to server")
                self.HOST = host #"192.168.43.203"
                self.PORT = int(port) #8080
                self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.s.connect((self.HOST, self.PORT))
                print("connected to server "+self.HOST+", port: "+str(self.PORT))
                
        def padMessage(self, payload, block_size, style = 'pkcs7'):
            padding_len = block_size - len(payload) % block_size
            if style == 'pkcs7':
                padding = bchr(padding_len) * padding_len
            elif style == 'x923':
                padding = bchr(0) * (padding_len-1) + bchr(padding_len)
            elif style == 'iso786':
                padding = bchr(128) + bchr(0) * (padding_len - 1)
            else:
                raise ValueError("Unknown Padding STyle")
        
            return payload + padding

        def sendMessage(self, text):
                try:
                        self.s.send(text)
                except any:
                        print()

class Raspberry():
        def __init__(self):
                self.threads = []
                self.buffer = CircularBuffer.CircularBuffer(30)
                self.curr_move = "nothing"

        def main(self):
                # Set up port connection
                self.port=serial.Serial("/dev/serial0", baudrate=115200)
                self.port.reset_input_buffer()
                self.port.reset_output_buffer()

                # Handshaking
                while(self.port.in_waiting == 0 or self.port.read() != 'A'):
                    print ('Try to connect to Arduino')
                    self.port.write('S')
                    time.sleep(1)
                self.port.write('A');
                print ('Connected')
                
                powerList = [0,0,0,0]

                #receive data thread
                receiveDataThread = ReceiveData(self.buffer, self.port, 0.03, 120)
                self.threads.append(receiveDataThread)

                #comms thread
                client = clientComms(powerList, current_move)
                self.threads.append(client)

                #store data thread
                storeDataThread = storeData(self.buffer, self.port, powerList, current_move, client)
                self.threads.append(storeDataThread)
                
                # Start threads
                for thread in self.threads:
                    # thread.daemon = True # Runs in background
                    thread.start()

if __name__ == '__main__':
        pi = Raspberry()
        pi.main()
        # client = clientComms()
        # client.main()
