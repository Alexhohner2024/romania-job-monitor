import json, os, gspread
c = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])
w = gspread.service_account_from_dict(c).open_by_key(os.environ['GOOGLE_SHEET_ID']).sheet1
v = w.get_all_values()
print(f'ROWS: {len(v)}')
for i, r in enumerate(v):
    print(f'{i}: {r}')
