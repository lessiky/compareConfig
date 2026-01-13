import openpyxl

try:
    wb = openpyxl.load_workbook('d:\\soft\\programs\\compareConfig\\hosts.xlsx')
    sheet = wb.active
    
    print("Headers:")
    for cell in sheet[1]:
        print(cell.value)
        
    print("\nFirst row data:")
    for cell in sheet[2]:
        print(cell.value)
except Exception as e:
    print(e)
