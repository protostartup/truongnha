# -*- coding: utf-8 -*-
from models import sms
import settings
import os
from django.core import mail
from suds.client import Client
from celery import task

def to_ascii(string):
    result = ''
    uni_a = u'ăắẳẵặằâầấẩẫậàáảãạ'
    uni_A = u'ĂẮẲẴẶẰÂẦẤẨẪẬÀÁẢÃẠ'
    uni_o = u'óòỏõọơớờởỡợôốồỗộổ'
    uni_O = u'ÓÒỎÕỌƠỚỜỞỠỢÔỐỒỖỘỔ'
    uni_i = u'ìĩịỉí'
    uni_I = u'ÌĨỊỈÍ'
    uni_u = u'ủùũụúưừứựữử'
    uni_U = u'ỦÙŨỤÚƯỪỨỰỮỬ'
    uni_e = u'éèẽẻẹêếềễệể'
    uni_E = u'ÉÈẼẺẸÊẾỀỄỆỂ'
    uni_y = u'ýỳỷỹỵ'
    uni_Y = u'ÝỲỶỸỴ'
    uni_d = u'đ'
    uni_D = u'Đ'

    for c in string:
        for cc in ['a','o','i','u','e','d','y','A','O','I','U','E','D','Y']:
            exec("if c in uni_" + cc + ": c = " + "'" + cc + "'" )
        result += c
    return result

@task()
def temp(subject, message, from_addr=None, to_addr=[]):
    mail.send_mail(settings.EMAIL_SUBJECT_PREFIX + subject,
            message,
            settings.EMAIL_HOST_USER,
            to_addr)

def send_email(subject, message, from_addr=None, to_addr=[]):
    #msg = MIMEText(message.encode('utf-8'), _charset='utf-8')
    #server = smtplib.SMTP('smtp.gmail.com',587) #port 465 or 587
    #server.ehlo()
    #server.starttls()
    #server.ehlo()
    #server.login(GMAIL_LOGIN,GMAIL_PASSWORD)
    #for to_address in to_addr:
    #    msg['Subject'] = subject
    #    msg['From'] = from_addr
    #    msg['To'] = to_address
    #    server.sendmail(from_addr, to_address, msg.as_string())
    #server.close()
    return temp.delay(subject, message,  from_addr, to_addr)
    
def sendSMS(phone, content, user, save_to_db=True):
    phone = checkValidPhoneNumber(phone)
    school = user.userprofile.organization
    if school.id in [42, 44]: raise Exception('NotAllowedSMS')
    if phone:
        url = settings.SMS_WSDL_URL
        username = settings.WSDL_USERNAME
        password = settings.WSDL_PASSWORD
        mt_username = settings.MT_USERNAME
        mt_password = settings.MT_PASSWORD
        content = to_ascii(u'Truong ' + unicode(school) + u' thong bao:' + '\n' + content)
        s = None
        if save_to_db:
            s = sms(phone=phone, content=content,
                    sender=user, recent=True, success=True)
            s.save()
        client = Client(url, username = username, password = password)
        message = \
    '''<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
<soap12:Body>
<InsertMT xmlns="http://tempuri.org/">
  <User>%s</User>
  <Pass>%s</Pass>
  <CPCode>160</CPCode>
  <RequestID>4</RequestID>
  <UserID>%s</UserID>
  <ReceiveID>%s</ReceiveID>
  <ServiceID>8062</ServiceID>
  <CommandCode>CNHN1</CommandCode>
  <ContentType>0</ContentType>
<Info>%s</Info>
</InsertMT>
</soap12:Body>
</soap12:Envelope>''' % (mt_username, mt_password, phone, phone, content)
        result = client.service.InsertMT(__inject= {'msg': str(message)})
        if result != '1' and save_to_db:
            s.success = False
            s.save()
        return result
    else:
        raise Exception("InvalidPhoneNumber")

def checkValidPhoneNumber(phone):
    if not int(phone[0]):
        phone = '84' + phone[1:]
        return phone
    elif phone[:2] != '84':
        return None
    else:
        return phone

def save_file(file):
    saved_file = open(os.path.join(settings.TEMP_FILE_LOCATION, 'sms_input.xls'), 'wb+')
    for chunk in file.chunks():
        saved_file.write(chunk)
    saved_file.close()
    return 'sms_input.xls'
