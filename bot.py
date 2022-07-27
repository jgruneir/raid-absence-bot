import os
import sys
import requests
import datetime
import json

import discord
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from google.oauth2 import service_account

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = 'credentials.json'

def updateCredsFromEnv():
	with open('credentials.json', 'r') as f:
	    print(f.read())
	data = None
	with open("credentials.json", "r") as jsonFile:
	    data = json.load(jsonFile)

	data["private_key_id"] = os.getenv("PRIVATE_KEY_ID")
	data["private_key"] = os.getenv("PRIVATE_KEY")
	data["client_email"] = os.getenv("CLIENT_EMAIL")
	data["client_id"] = os.getenv("CLIENT_ID")

	with open("credentials.json", "w") as jsonFile:
		jsonFile.write(json.dumps(data).replace('\\\\', '\\'))
	with open('credentials.json', 'r') as f:
		print(f.read())

updateCredsFromEnv()
credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

# The ID and range of the spreadsheet.
SPREADSHEET_ID = '16JgFZjcDEtND5U25cudjrm3EVZtlrtMrB0CZGWYdOLk'
RANGE_NAME = 'Sheet1'

TOKEN = os.getenv('DISCORD_TOKEN')

client = discord.Client()

sheetService = None

@client.event
async def on_ready():
	print(f'{client.user} has connected to Discord!')
	initSheets()

@client.event
async def on_message(message):
	print(message.content)

	if message.author == client.user:
		return

	messageLower = message.content.lower()

	#Message Formats:
	#Absent: Dryeck: 7/16
	#Absent: Dryeck: 7/16, 7/18
	#Absent: Dryeck: 7/16,7/18
	#Absent: Dryeck: 7/16 - 7/18
	#Absent: Dryeck: 7/16-7/18
	#Absent: Dryeck: 7/16 - 7/19: notes go here
	#Late: Dryeck: 7/16: notes go here
	if str(message.channel) == "absences" and (messageLower.startswith ("absent:") or messageLower.startswith("late:")):
		await message.add_reaction("🔄")
		res = updateSheetWithAbsence(message.content)
		if res == "Noted!":
			await message.clear_reaction("🔄")
			await message.add_reaction("✅")
		else: 
			await message.clear_reaction("🔄")
			await message.add_reaction("❌")
		await message.channel.send(res)
		updateDateColors()

def updateSheetWithAbsence(info):
	colonSplit = info.split(":")

	if len(colonSplit) < 3:
		return "Invalid format: <Absent/Late>: <Name>: <Date(s)>: <Note>"
	elif len(colonSplit[1].strip()) == 0:
		return "Missing name"
	elif len(colonSplit[2].strip()) < 3:
		return "No dates provided"

	absentType = colonSplit[0].strip()
	name = colonSplit[1].strip()
	datesAbsent = colonSplit[2].strip()
	notes = None

	if len(colonSplit) > 3:
		notes = colonSplit[3].strip()
	if "-" in datesAbsent:
		handleDateRangeAbsences(datesAbsent, absentType, name, notes)
	elif "," in datesAbsent:
		commaSplit = datesAbsent.split(",")
		for date in commaSplit:
			print("adding absent row: " + date.strip())
			addAbsenceRow(absentType, name, date.strip(), notes)
	else:
		addAbsenceRow(absentType, name, datesAbsent, notes)
	
	return "Noted!"

def handleDateRangeAbsences(datesAbsent, absentType, name, notes):
	dashSplit = datesAbsent.split("-")
	if len(dashSplit) != 2:
		return "Invalid date format"
	today = datetime.date.today()
	tf = today.strftime("%m/%d/%Y")
	absentDateStartString = dashSplit[0].strip() + "/" + tf.split("/")[2]
	absentDateStart = datetime.datetime.strptime(absentDateStartString, '%m/%d/%Y')
	absentDateEndString = dashSplit[1].strip() + "/" + tf.split("/")[2]
	absentDateEnd = datetime.datetime.strptime(absentDateEndString, '%m/%d/%Y')

	if absentDateEnd <= absentDateStart:
		return "End date after start date"

	while absentDateStart <= absentDateEnd:
		print("adding absent row: " + datetime.datetime.strftime(absentDateStart, "%m/%d/%Y"))
		addAbsenceRow(absentType, name, datetime.datetime.strftime(absentDateStart, "%m/%d"), notes)
		absentDateStart = absentDateStart + datetime.timedelta(days=1)

def addAbsenceRow(absentType, name, date, notes):
	body = {'values': [[absentType,name,date,notes]]}
	sheetService.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME, valueInputOption="RAW", body=body).execute()

def updateDateColors():
	today = datetime.date.today()
	tf = today.strftime("%m/%d/%Y")

	values = getSheetData("Sheet1!A2:C")

	for idx, row in enumerate(values):
		print(str(idx))
		if len(row) > 2 and row[2] is not None and len(row[2]) > 2:
			rowDateString = row[2] + "/" + tf.split("/")[2]
			rowDate = datetime.datetime.strptime(rowDateString, '%m/%d/%Y').date()
			if rowDate < today:
				markDatePassed(idx)

def markDatePassed(idx):
	body = {
		"requests": [
			{
				"repeatCell": {
					"range": {
						"sheetId": 0,
						"startRowIndex": idx+1,
						"endRowIndex": idx+2,
						"startColumnIndex": 0,
						"endColumnIndex": 4
					},
					"cell": {
						"userEnteredFormat": {
							"backgroundColor": {
								"red": 180 / 255,
								"green": 95 / 255,
								"blue": 6 / 255
							}
						}
					},
					"fields": "userEnteredFormat.backgroundColor"
				}
			}
		]
	}
	response = sheetService.spreadsheets().batchUpdate(
			spreadsheetId=SPREADSHEET_ID,
			body=body).execute()

def getSheetData(rangeInput):
	result = sheetService.spreadsheets().values().get(
			spreadsheetId=SPREADSHEET_ID, range=rangeInput).execute()
	values = result.get('values', [])

	if not values:
		return('No data found.')
	return values

def initSheets():
	global sheetService
	try:
		sheetService = build('sheets', 'v4', credentials=credentials)
	except HttpError as err:
		print(err)

client.run(TOKEN)