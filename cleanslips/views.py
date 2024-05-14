# django imports
from django.shortcuts import render, redirect
from django.http import HttpResponseBadRequest, HttpResponse
from django import forms
from operator import itemgetter
from io import StringIO, BytesIO
import os
import re

# local imports
from . import helpers
from . modules import callnumber
from . modules.docx_mailmerge_local.mailmerge import MailMerge

# form class
class UploadFileForm(forms.Form):
    file = forms.FileField()


# main upload and processing form #############################################
def upload(request, campus, template):

    # get campus name
    campus_name = helpers.get_campus_name(campus)
    if campus_name == None:
        return render(request, 'errors.html', {'title' : 'IDS Slips | Ooops',
                                               'campus': campus.upper(),
                                               'template': template,
                                               'errors' : f"Campus code '{campus.upper()}' was not found. Are you sure you have your correct 3 character campus code?"},
                                               )

    # serve up upload form
    if request.method == 'GET':
        file = forms.FileField()
        form = UploadFileForm()
        return render(request, 'upload.html', {'form': form,
                                               'title': 'IDS Slips | '+campus_name,
                                               'header': ('IDS Slips'),
                                               'campus': campus.upper(),
                                               'campus_name': campus_name})

    # get spreadsheet
    if request.method == "POST":
        form = UploadFileForm(request.POST, request.FILES)

        if form.is_valid():
            filehandle = request.FILES['file']

            # Check file type
            if ".xls" not in str(filehandle):
                return render(request, 'errors.html', {'title' : 'IDS Slips | Ooops',
                                                       'campus': campus.upper(),
                                                       'template': template,
                                                       'errors' : "Chosen file is not an .xls file. Are you sure that you chose LendingRequestReport.xls?"},
                                                       )

            # read spreadsheet
            ill_requests = []

            # check header
            rows = filehandle.get_array()
            """
            ['Title', 'Author', 'Publisher', 'Publication date', 'Barcode', 'ISBN/ISSN', 'Availability', 'Volume/Issue', 
             'Shipping note', 'Requester email', 'Pickup at', 'Electronic available', 'Digital available', 'External request ID', 
             'Partner name', 'Partner code', 'Copyright Status', 'Level of Service', 'Requested Barcode', 'Chapter Information', 
             'Journal Title', 'Page Numbers']

            if rows[0] !=
            ['Title', 'Author', 'Publisher', 'Publication date', 'Barcode', 'ISBN/ISSN', 'Availability', 'Volume/Issue', 
             'Shipping note', 'Requester email', 'Pickup at', 'Electronic available', 'Digital available', 'External request ID', 
             'Partner name', 'Partner code', 'Copyright Status', 'Level of Service', 'Requested Barcode']:
            """
            if rows[0] != ['Title', 'Author', 'Publisher', 'Publication date', 'Barcode', 'ISBN/ISSN', 'Availability', 'Volume/Issue', 'Shipping note', 'Requester email', 'Pickup at', 'Electronic available', 'Digital available', 'External request ID', 'Partner name', 'Partner code', 'Copyright Status', 'Level of Service', 'Requested Barcode', 'Chapter Information', 'Journal Title', 'Page Numbers']:
                return render(request, 'errors.html', {'title' : 'IDS Slips | Ooops',
                                                       'campus': campus.upper(),
                                                       'template': template,
                                                       'errors' : "The headers on this spreadsheet don't match what IDS Slips is expecting. Are you sure that you chose LendingRequestReport.xls?"},
                                                       )

            # __________ PARSE SPREADSHEET ____________________________________
            for row in rows:

                # skip header
                if row[0] == "Title":
                    continue

                title = row[0]
                author = row[1]
                publisher = row[2]
                publication_date = row[3]
                barcode = row[4]
                isbn_issn = row[5]
                availability_string = row[6]
                volume_issue = row[7]
                requestor_email = row[9]
                pickup_at = row[10]
                electronic_available = row[11]
                digital_available = row[12]
                eri = row[13]
                eri = eri.split('//')[1:]
                eri = '//'.join(eri)
                external_request_id = eri
                partner_name = row[14]
                partner_code = row[15]
                copyright_status = row[16]
                level_of_service = row[17]

                # ___________ PARSE SHIPPING NOTE _____________________________
                shipping_note = row[8]
                shipping_notes = shipping_note.split('||')
                try:
                    comments = shipping_notes[0]
                    requestor_name = shipping_notes[1]
                except:
                    #print(f"SHIPPING NOTE FIELD - {shipping_note} - IS NOT AS EXPECTED...ATTEMPTING TO COMPENSATE...")
                    comments = ""
                    requestor_name = shipping_note
                    
                # __________ PARSE AVAILABILITY _______________________________
                availability_array = availability_string.split('||')

                full_availability_array = []
                full_sort_string_array = []

                for availability in availability_array:

                    # skip if on loan
                    if "Resource Sharing Long Loan" in availability:
                        continue
                    if "Resource Sharing Short Loan" in availability:
                        continue

                    # split availability string into parts
                    regex = r'(.*?),(.*?)\.(.*).*(\(\d{1,3} copy,\d{1,3} available\))'
                    q = re.findall(regex, availability)
                    try:
                        matches = list(q[0])
                        
                        library = matches[0]
                        location = matches[1]
                        call_number = matches[2]
                        holdings = matches[3]

                        full_availability_array.append(f"[{location} - {call_number[:-1]}]") # negative index to remove extra space

                    except IndexError:
                        library = None
                        location = None
                        call_number = None
                        holdings = None
                        full_availability_array.append(f"[{availability}]")

                    # normalize call number for sorting
                    try:
                        lccn = callnumber.LC(call_number)
                        lccn_components = lccn.components(include_blanks=True)
                        normalized_call_number = lccn.normalized
                    except:
                        #print(f"CALL NUMBER - {call_number} - IS NOT VALID LC. ATTEMPTING TO COMPENSATE...")
                        normalized_call_number = None
                    
                    if normalized_call_number == None:
                        normalized_call_number = call_number
                    
                    # generate sort string
                    sort_string = f"{location}|{normalized_call_number}"
                    full_sort_string_array.append(sort_string)

                # combine availability and sort fields
                full_availability = "; ".join(full_availability_array)
                full_sort_string = "; ".join(full_sort_string_array)

                # __________ ADD TO REQUESTS DICTIONARY _______________________
                ill_request = {
                    'Partner_name' : partner_name,
                    'Partner_Code' : partner_code,
                    'External_request_ID' : external_request_id,
                    'Availability' : full_availability,
                    'Call_Number' : call_number,
                    'Comments' : comments,
                    'RequestorName' : requestor_name,
                    'VolumeIssue' : volume_issue,
                    'Title' : title[:40],
                    'Shipping_note' : requestor_name,
                    'Sort' : sort_string,
                    'Campus_Code': campus,
                    'Campus_Name': campus_name,
                }

                # add to ongoing list
                ill_requests.append(ill_request)

            # sort requests by location and normalized call number
            requests_sorted = sorted(ill_requests, key=itemgetter('Sort'))

            # Inject lender/borrower address into requests for mail merge
            # - List must be XLSX saved as MS DOS CSV
            address_list = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                'static',
                'address_list.csv')
            req2 = []
            for req in requests_sorted:
                if req['Partner_Code'] == 'ILL': continue
                req['From_Institution'] = ''
                req['From_LibraryName'] = ''
                req['From_Address1'] = ''
                req['From_City'] = ''
                req['From_State'] = ''
                req['From_Zip'] = ''
                req['From_SYMBOL'] = ''
                req['From_HUB'] = ''
                req['To_Institution'] = ''
                req['To_LibraryName'] = ''
                req['To_Address1'] = ''
                req['To_City'] = ''
                req['To_State'] = ''
                req['To_Zip'] = ''
                req['To_SYMBOL'] = ''
                req['To_HUB'] = ''
                with open(address_list) as fin:
                    for line in fin:
                        line = line.split(',')
                        if line[0] == req['Campus_Code']:
                            req['From_Institution'] = line[2]
                            req['From_LibraryName'] = line[3]
                            req['From_Address1'] = line[4]
                            req['From_City'] = line[5]
                            req['From_State'] = line[6]
                            req['From_Zip'] = line[7]
                            req['From_SYMBOL'] = line[9]
                            req['From_HUB'] = line[8]
                        if line[1] == req['Partner_Code']:
                            req['To_Institution'] = line[2]
                            req['To_LibraryName'] = line[3]
                            req['To_Address1'] = line[4]
                            req['To_City'] = line[5]
                            req['To_State'] = line[6]
                            req['To_Zip'] = line[7]
                            req['To_SYMBOL'] = line[9]
                            req['To_HUB'] = line[8]
                req2.append(req)
            requests_sorted = req2

            # _________ GENERATE LABELS _______________________________________
            
            # stickers
            if template == "stickers":
                template = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.join('static','slip_templates','campus',campus.upper(),'TEMPLATE_stickers.docx'))
                document = MailMerge(template)
                document.merge_rows('Shipping_note', requests_sorted)

            # flags
            if template == "flags":
                #template = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.join('static','slip_templates','campus', campus.upper(), 'TEMPLATE_flags.docx'))
                template = os.path.join(os.path.dirname(os.path.realpath(__file__)),'static','slip_templates','template_suny_flag.docx')
                document = MailMerge(template)
                document.merge_templates(requests_sorted, separator='column_break')

            # generate slips in memory and send as attachment
            f = BytesIO()
            document.write(f)
            length = f.tell()
            f.seek(0)
            response = HttpResponse(
                f.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = 'attachment; filename=SLIPS.docx'
            response['Content-Length'] = length
            
            return response



# Other pages #################################################################
def home(request):
    return render(request, 'home.html', {f'title': 'IDS Slips | Home',
                                         'header': 'IDS Slips'})

def find(request):
    if request.POST:
        return redirect(f"/campus={request.POST['campus']}&template={request.POST['template']}")
    else:
        return render(request, 'errors.html', {'title': 'IDS Slips | Ooops!',
                                                 'header': 'IDS Slips'})

def docs(request):
    return render(request, 'docs.html', {'title': 'IDS Slips | Documentation',
                                         'header': 'IDS Slips'})

def contact(request):
    return render(request, 'contact.html', {'title': 'IDS Slips | Contact',
                                         'header': 'IDS Slips'})
