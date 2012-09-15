#! /usr/bin/env python
#encoding:UTF-8
from django.core.urlresolvers import reverse
from base_tests import SchoolSetupTest, AddStudentTest
from school.models import DiemDanh
import simplejson
from datetime import date
# Loi test nho chu y: test ca get, post. Khi post thi nen test add subject ca
# nhung mon quan trong nhu: Toan, Van, kiem tra he so, kiem tra diem kem theo
# ung voi mon do cho tung hoc sinh trong lop
class AddSubjectTest(SchoolSetupTest):
    def phase8_get_subjects_of_class(self):
        classes = self.year.class_set.order_by('id')
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        #go to subjects per class
        res = self.client.get(reverse('subject_per_class', args=[cl.id]))
        print 'Going to check response status code'
        self.assertEqual(res.status_code, 200)
        print 'Going to check response content'
        context = res.context
        self.assertEqual(context['class'].id, cl.id)

    def phase9_add_a_subject(self):
        classes = self.year.class_set.order_by('id')
        #teachers = self.school.teacher_set.all()
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]

        response = self.client.post(
            reverse('subject_per_class',args=[cl.id]),
                {
                'request_type': u'add',
                'name': u'Mĩ thuật test',
                'hs' : u'1',
                'teacher_id' : u'',
                'number_lesson': u'1',
                'nx' : u'on',
                'primary' : u'0',
                'type' : u'Mĩ thuật',
                },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        print 'Going to check response content type'
        self.assertEqual(response['Content-Type'], 'json')
        print 'Going to check response content'
        cont = simplejson.loads(response.content)
        self.assertEqual(cont['success'], True)
        self.assertEqual(cont['message'],u'Môn học mới đã được thêm.')

    def phase10_delete_a_subject(self):
        classes = self.year.class_set.order_by('id')
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        sub = cl.subject_set.get(name = u'Mĩ thuật test')
        response = self.client.post(
            reverse('subject_per_class',args=[cl.id]),
                {
                'request_type': u'xoa',
                'id' : sub.id,
                },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        print 'Going to check response content type'
        self.assertEqual(response['Content-Type'], 'json')
        print 'Going to check response content'
        cont = simplejson.loads(response.content)
        self.assertEqual(cont['message'], u'Đã xóa thành công.')
    def phase12_delete_toan_or_nguvan(self):
        classes = self.year.class_set.order_by('id')
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        sub = cl.subject_set.get(type = u'Toán')
        response = self.client.post(
            reverse('subject_per_class',args=[cl.id]),
                {
                'request_type': u'xoa',
                'id' : sub.id,
                },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        print 'Going to check response content type'
        self.assertEqual(response['Content-Type'], 'json')
        print 'Going to check response content'
        cont = simplejson.loads(response.content)
        self.assertEqual(cont['message'], u'Bad request.')
    def phase13_modify_subject(self):
        classes = self.year.class_set.order_by('id')
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        sub = cl.subject_set.get(type = u'Toán')
        print 'Update with negative heso'
        response = self.client.post(
            reverse('subject_per_class',args=[cl.id]),
                {
                'request_type': u'hs',
                'hs' : u'-1',
                'id' : sub.id,
                },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        print 'Going to check response content type'
        self.assertEqual(response['Content-Type'], 'json')
        print 'Going to check response content'
        cont = simplejson.loads(response.content)
        self.assertEqual(cont['message'], u'Hệ số không được nhỏ hơn 0')

        print 'Update with valid heso'
        response = self.client.post(
            reverse('subject_per_class',args=[cl.id]),
                {
                'request_type': u'hs',
                'hs' : u'2',
                'id' : sub.id,
                },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        print 'Going to check response content type'
        self.assertEqual(response['Content-Type'], 'json')
        print 'Going to check response content'
        cont = simplejson.loads(response.content)
        self.assertEqual(cont['message'], u'Cập nhật thành công.')
        
class DiemDanhTest(AddStudentTest):
    def diemdanh_a_student(self, cl, st, t, today):
        data=''
        data+= '-'.join([ str(st.id), t,
            str(today.day),
            str(today.month),
            str(today.year)]) + '%'
        res = self.client.post(reverse('dd',
            args=[cl.id, today.day, today.month, today.year]), {
                'data': data,
                'request_type': 'dd',
                }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        print 'Going to check response status'
        self.assertEqual(res.status_code, 200)
        print 'Going to check database'
        dd_list = DiemDanh.objects.filter(
                student_id=st,
                time=today)
        if t:
            self.assertEqual(len(dd_list), 1)
        else:
            self.assertEqual(len(dd_list), 0)
        for dd in dd_list:
            self.assertEqual(dd.loai, t)
        print 'Going to check update dd to %s' % t

    def phase12_add_diem_danh(self):
        cl = self.year.class_set.all()
        self.assertEqual(len(cl)>=1, True)
        cl = cl[0]
        today = date.today()
        res = self.client.get(reverse('dd',
            args=[cl.id, today.day, today.month, today.year]))
        print 'Going to check response status'
        self.assertEqual(res.status_code, 200)
        print 'Going to check response content'
        context = res.context
        print 'Going to check response context'
        self.assertEqual(context['class'].id, cl.id)
        self.assertEqual(context['date'], today)
        # done check get request
        sts = cl.students()
        types = ['K', 'P', '']
        for st in sts:
            for t in types:
                self.diemdanh_a_student(cl, st, t, today)    

class HanhKiemTest(AddStudentTest):
    def phase12_enter_hk_page(self):
        classes = self.year.class_set.all()
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        #go to subjects per class
        res = self.client.get(reverse('hanh_kiem', args=[cl.id]))
        print 'Going to check response status'
        self.assertEqual(res.status_code, 200)
        print 'Going to check response context'
        self.assertEqual(res.context['class'].id,cl.id)

    def phase13_edit_current_term_hk(self):
        term = self.year.term_set.get(number = self.school.status)
        classes = self.year.class_set.all()
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        student = cl.students()[0]
        request_type = 'term' + str(term.number)
        res = self.client.post(reverse('hanh_kiem',
            args=[cl.id]), {
            'request_type': request_type,
            'id': student.id,
            'val':u'T',
            }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        print 'Going to check response status'
        self.assertEqual(res.status_code, 200)
        print 'Going to check response content type'
        self.assertEqual(res['Content-Type'], 'json')
        cont = simplejson.loads(res.content)
        print 'Going to check response content'
        self.assertEqual(cont['success'],True)
        hk = student.tbnam_set.get(year_id__exact= self.year.id)
        print 'Going to check if hk is save'
        self.assertEqual(hk.term1,'T')
        res = self.client.post(reverse('hanh_kiem',
            args=[cl.id]), {
            'request_type': u'hk_thang_10',
            'id': student.id,
            'val':u'T',
            }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        print 'Going to check response status'
        self.assertEqual(res.status_code, 200)
        print 'Going to check response content type'
        self.assertEqual(res['Content-Type'], 'json')
        cont = simplejson.loads(res.content)
        print 'Going to check response content'
        self.assertEqual(cont['success'],True)
        hk = student.tbnam_set.get(year_id__exact= self.year.id)
        print 'Going to check if hk is save'
        self.assertEqual(hk.hk_thang_10,u'T')

class KhenThuongTest(AddStudentTest):
    def phase12_add_khenthuong(self):
        classes = self.year.class_set.all()
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        self.assertGreater(len(cl.students()),0)
        student = cl.students()[0]
        num_kt = student.khenthuong_set.count()
        self.assertEqual(num_kt,0)
        res = self.client.post(reverse('add_khen_thuong',args=[student.id]),{
            'hinh_thuc':u'Khen trước lớp',
            'dia_diem':'',
            'noi_dung':'',
            'time': date.today().strftime("%d/%m/%Y")
        })
        print 'Going to check response status'
        self.assertEqual(res.status_code, 302)
        print 'Going to check response content type'
        self.assertEqual(res['Content-Type'],'text/html; charset=utf-8')
        print 'Going to check if kt is save'
        num_kt = student.khenthuong_set.count()
        self.assertEqual(num_kt,1)

    def phase13_edit_khenthuong(self):
        classes = self.year.class_set.all()
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        self.assertGreater(len(cl.students()),0)
        student = cl.students()[0]
        kts = student.khenthuong_set.all()
        self.assertEqual(kts.count(),1)
        kt = kts[0]
        res = self.client.post(reverse('edit_khen_thuong',args=[kt.id]),{
            'hinh_thuc':u'Được khen thưởng đặc biệt',
            'dia_diem':u'HN',
            'noi_dung':'',
            'time': date.today().strftime("%d/%m/%Y")
        })
        print 'Going to check response status'
        self.assertEqual(res.status_code, 302)
        print 'Going to check response content type'
        self.assertEqual(res['Content-Type'],'text/html; charset=utf-8')
        print 'Going to check if kt is save'
        kt = student.khenthuong_set.all()[0]
        self.assertEqual(kt.dia_diem,u'HN')
        self.assertEqual(kt.hinh_thuc,u'Được khen thưởng đặc biệt')

    def phase14_delete_khenthuong(self):
        classes = self.year.class_set.all()
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        self.assertGreater(len(cl.students()),0)
        student = cl.students()[0]
        kts = student.khenthuong_set.all()
        self.assertEqual(kts.count(),1)
        kt = kts[0]
        res = self.client.get(reverse('delete_khen_thuong',args=[kt.id]))
        print 'Going to check response status'
        self.assertEqual(res.status_code, 302)
        print 'Going to check response content type'
        self.assertEqual(res['Content-Type'],'text/html; charset=utf-8')
        print 'Going to check if kt is delete'
        num_kt = student.khenthuong_set.count()
        self.assertEqual(num_kt,0)

class KiLuatTest(AddStudentTest):
    def phase12_add_kiluat(self):
        classes = self.year.class_set.all()
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        self.assertGreater(len(cl.students()),0)
        student = cl.students()[0]
        num_kl = student.kiluat_set.count()
        self.assertEqual(num_kl,0)
        res = self.client.post(reverse('add_ki_luat',args=[student.id]),{
            'hinh_thuc':u'Khiển trách trước hội đồng kỷ luật',
            'dia_diem':'',
            'noi_dung':'',
            'time': date.today().strftime("%d/%m/%Y")
        })
        print 'Going to check response status'
        self.assertEqual(res.status_code, 302)
        print 'Going to check response content type'
        self.assertEqual(res['Content-Type'],'text/html; charset=utf-8')
        print 'Going to check if kt is save'
        num_kl = student.kiluat_set.count()
        self.assertEqual(num_kl,1)
    def phase13_edit_kiluat(self):
        classes = self.year.class_set.all()
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        self.assertGreater(len(cl.students()),0)
        student = cl.students()[0]
        kls = student.kiluat_set.all()
        self.assertEqual(kls.count(),1)
        kl = kls[0]
        res = self.client.post(reverse('edit_ki_luat',args=[kl.id]),{
            'hinh_thuc':u'Đình chỉ học',
            'dia_diem':u'TB',
            'noi_dung':'',
            'time': date.today().strftime("%d/%m/%Y")
        })
        print 'Going to check response status'
        self.assertEqual(res.status_code, 302)
        print 'Going to check response content type'
        self.assertEqual(res['Content-Type'],'text/html; charset=utf-8')
        print 'Going to check if kl is save'
        kl = student.kiluat_set.all()[0]
        self.assertEqual(kl.dia_diem,u'TB')
        self.assertEqual(kl.hinh_thuc,u'Đình chỉ học')

    def phase14_delete_kiluat(self):
        classes = self.year.class_set.all()
        # get a class
        self.assertEqual(len(classes)>0, True)
        cl = classes[0]
        self.assertGreater(len(cl.students()),0)
        student = cl.students()[0]
        kls = student.kiluat_set.all()
        self.assertEqual(kls.count(),1)
        kl = kls[0]
        res = self.client.get(reverse('delete_ki_luat',args=[kl.id]))
        print 'Going to check response status'
        self.assertEqual(res.status_code, 302)
        print 'Going to check response content type'
        self.assertEqual(res['Content-Type'],'text/html; charset=utf-8')
        print 'Going to check if kt is delete'
        num_kl = student.kiluat_set.count()
        self.assertEqual(num_kl,0)

class ImportStudentTest(SchoolSetupTest):
    def phase8_get_a_class(self):
        classes = self.year.class_set.all()
        self.assertEqual(len(classes)>0, True)
        self.cl = classes[0]
        res = self.client.get(reverse('class_detail', args=[self.cl.id]))
        self.assertEqual(res.status_code, 200)
    def phase9_import_5_students(self):
        with open('school/unittests/import_5_student.xls', 'rb') as input_file:
            res = self.client.post(
                    reverse('student_import', args=[self.cl.id,'import']),
                    {
                        'name': 'import file',
                        'files[]': [input_file]
                    })
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res['Content-Type'], 'json')
            content = simplejson.loads(res.content)
            content = content[0]
            self.assertEqual(content['number'], 5)
            self.assertEqual(content['number_ok'], 5)
            self.assertEqual(content['message'], u'Nhập dữ liệu thành công')
            self.assertEqual(content['student_confliction'], '')
    def phase10_import_5_duplicated_students(self):
        with open('school/unittests/import_5_student.xls', 'rb') as input_file:
            res = self.client.post(
                    reverse('student_import', args=[self.cl.id,'import']),
                    {
                        'name': 'import file',
                        'files[]': [input_file]
                    })
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res['Content-Type'], 'json')
            content = simplejson.loads(res.content)
            content = content[0]
            self.assertEqual(content['number'], 5)
            self.assertEqual(content['number_ok'], 0)
            existing_student = self.client.session['saving_import_student']
            self.assertEqual(len(existing_student), 5)
            res = self.client.post(
                    reverse('student_import', args=[self.cl.id, 'update']),
                    {},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res['Content-Type'], 'json')
            content = simplejson.loads(res.content)
            self.assertEqual(content['success'], True)
            self.assertEqual(content['message'], u'Thông tin không thay đổi')
