import json, os, gspread
creds = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])
client = gspread.service_account_from_dict(creds)
ws = client.open_by_key(os.environ['GOOGLE_SHEET_ID']).sheet1
vals = ws.get_all_values()
print(f'ROWS: {len(vals)}')
for i,r in enumerate(vals):
    print(f'{i}: {r}')
