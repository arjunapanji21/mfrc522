#!/usr/bin/env python3

# import libraries
import os
import math
import serial
import numpy as np
import pygame
import busio
import board
import requests
import adafruit_amg88xx
import RPi.GPIO as GPIO
import mysql.connector
from mysql.connector import Error
from requests_toolbelt import MultipartEncoder
from time import sleep
from scipy.interpolate import griddata
from colour import Color
from mfrc522 import SimpleMFRC522

try:
    # database connection
    db = mysql.connector.connect(
            host = "localhost",
            user = "root",
            password = "",
            database = "dbName")

    db_cursor = db.cursor()
except Error as e:
    print("\nWarning!! Database connection error at {} \n".format(e))

# set pin buzzer 23 as output
buzzer = 23
GPIO.setmode(GPIO.BCM)
GPIO.setup(buzzer, GPIO.OUT)
GPIO.setwarnings(False)

# serial lcd
ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
ser.flush()

# url website
url = 'http://ceksuhu.go-web.my.id/index.php'

# check amg8833
os.system('i2cdetect -y 1')

# initialize amg8833
i2c_bus = busio.I2C(board.SCL, board.SDA)
sensor = adafruit_amg88xx.AMG88XX(i2c_bus)

# RFID Reader
rfid = SimpleMFRC522()

# configure amg8833 sensor
MINTEMP = 27.0 # blue
MAXTEMP = 32.0 # red
COLORDEPTH = 1024
os.putenv('SDL_FBDEV', '/dev/fb1')
pygame.init()
font = pygame.font.Font('freesansbold.ttf',28)
points = [(math.floor(ix/8), (ix%8)) for ix in range(0,64)]
grid_x, grid_y = np.mgrid[0:7:32j, 0:7:32j]
height = 480
width = 480
blue = Color('indigo')
colors = list(blue.range_to(Color("red"), COLORDEPTH))
colors = [(int(c.red * 255), int(c.green * 255), int(c.blue * 255)) for c in colors]
displayPixelWidth = width / 30
displayPixelHeight = height / 30

# insert image to database
def insertBlob(filePath):
    with open(filePath, "rb") as File:
        data = File.read()
    sql = "INSERT INTO images (Photo) VALUES (%s)"
    db_cursor.execute(sql, (data,))
    db.commit()

# some utility functions for amg8833
def constrain(val, min_val, max_val):
    return min(max_val, max(min_val, val))
def map_value(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

# activate beep
def beep():
    GPIO.output(buzzer, GPIO.HIGH)
    sleep(0.1)
    GPIO.output(buzzer, GPIO.LOW)
    sleep(0.1)

# lcd ready
ready = False

while(True):
    # read serial from arduino
    if(ser.in_waiting > 0):
        data = ser.readline().decode('utf-8').rstrip()
        print(data)
        
        if(data == "Ready"):
            ser.write(b"  SCAN ID CARD\n")
            print("Press CTRL+C to Exit Program")
            sleep(0.5)
            ready = True
    
    if(ready == True):
        try:
            id, text = rfid.read()
            if(id != None):
                beep()
                ser.write("ID: {}\n".format(id).encode('utf-8'))
                pygame.display.set_caption('Thermal Cam')
                lcd = pygame.display.set_mode((width, height))
                lcd.fill((255,0,0))
                pygame.display.update()

                sleep(1)
                userId = id
                count = 20
    
                #GPIO.output(buzzer, GPIO.LOW)
                while(userId == id): 
                    # send message to arduino
                    ser.write(b"SCANNING SUHU..\n")

                    # read the pixels
                    pixels = []
                    for row in sensor.pixels:
                        pixels = pixels + row
                    pixels = [map_value(p, MINTEMP, MAXTEMP, 0, COLORDEPTH - 1)for p in pixels]
                    
                    # perform interpolation
                    bicubic = griddata(points, pixels, (grid_x, grid_y), method="cubic")

                    # draw everything
                    for ix, row in enumerate(bicubic):
                        for jx, pixel in enumerate(row):
                            pygame.draw.rect(
                                    lcd,
                                    colors[constrain(int(pixel), 0, COLORDEPTH - 1)],
                                    (
                                        displayPixelHeight * ix,
                                        displayPixelWidth * jx,
                                        displayPixelHeight,
                                        displayPixelWidth,
                                        ),
                            )
                    list = pixels
                    maxTemp = max(list)

                    # create text surface
                    temp = maxTemp/MAXTEMP
                    text = font.render("Suhu: "+str(temp)+" °C", True, (255,255,255))
                    textRect = text.get_rect()
                    lcd.blit(text, textRect)

                    pygame.display.update()
                    count -= 1
                    #print(count)
                    if (temp < 20):
                        count = 20

                    if (count <= 0):
                        count = 0

                        beep()
                        beep()

                        # send serial to arduino
                        ser.write("SUHU ANDA: {} C\n".format(temp).encode('utf-8'))
                        sleep(1)

                        pygame.image.save(lcd, '{}.jpg'.format(id))

                        #path_img = '{}.jpg'.format(id)
                        path_img = 'home/pi/Desktop/{}.jpg'.format(id)

                        #insertBlob(path_img)
                                              
                        # send data to website
                        #with open(path_img, 'rb') as img:
                        #    name_image = os.path.basename(path_img)
                        #    files = {'id': id,'suhu': temp,'image': img, 'multipart/form-data',{'Expires':'0'})}
                        #    with requests.Session() as s:
                        #        res = s.post(url, files=files)

                        query = {'id':id,'suhu':temp,'image':(path_img, 'rb')}
                        res = requests.post(url, data = query)
                        print("Berhasil mengirim data {} ke website".format(res.text))
                        print(res.status_code)
                        pygame.display.quit()
                        sleep(1)
                        ser.write(b"  SCAN ID CARD\n")
                        print("Press CTRL+C to Exit Program")
                        break
            
        finally:
            pass
            #GPIO.cleanup()

GPIO.cleanup()
