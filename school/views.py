﻿# coding=utf-8
# Create your views here.
from datetime import date
import datetime
import os
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, HttpResponseRedirect
from django.db import transaction
from django.db.models import Count
from django.shortcuts import render_to_response
from django.template import RequestContext, loader
from django.http import HttpResponseNotAllowed
from django.core.urlresolvers import reverse
from django.utils import simplejson
from django.contrib.auth import logout
from recaptcha.client import captcha
from app.models import SystemLesson, SUBJECT_CHOICES
from school.forms import UsernameChangeForm, SchoolForm,\
        SettingForm, TKDiemDanhForm, TKBForm, SelectSchoolLessonForm3,\
        SelectSchoolLessonForm2, LessonForm, ForgetPasswordForm
from school.models import UncategorizedClass, Term, Subject, Pupil,\
        Class, DiemDanh, StartYear, Year, Lesson, TKDiemDanh, TKB,\
        SchoolLesson, Block, Teacher, Attend, COMMENT_SUBJECT_LIST
from decorators import need_login, school_function, operating_permission,\
        year_started
from school.school_settings import CAP2_DS_MON, CAP1_DS_MON, CAP3_DS_MON
from school.utils import get_current_year, get_school, get_permission,\
        get_current_term, move_student, get_position, in_school,\
        inClass, get_teacher, to_date, get_lower_bound, get_upper_bound,\
        to_en1, add_subject, make_default_password, queryset_to_dict
from namesorting import multikeysort
from sms.utils import send_email, sendSMS
from school.helptools import sync_tkb_db
import settings

START_YEAR = os.path.join('school', 'start_year.html')
SCHOOL = os.path.join('school', 'school.html')
YEARS = os.path.join('school', 'years.html')
CLASS_LABEL = os.path.join('school', 'class_labels.html')
INFO = os.path.join('school', 'info.html')
SETUP = os.path.join('school', 'setup.html')
ORGANIZE_STUDENTS = os.path.join('school', 'organize_students.html')
STUDENT = os.path.join('school', 'classDetail_one_student.html')
NO_CONTACT = os.path.join('school','no_contact.html')

@need_login
@school_function
def school_index(request):
    user = request.user
    school = get_school(request)
    if not school.status:
        return HttpResponseRedirect(reverse('setup'))
    try:
        year = get_current_year(request)
    except Exception:
        return HttpResponseRedirect(reverse('setup'))

    user_type = get_permission(request)
    if user_type in ['HIEU_TRUONG', 'HIEU_PHO']:
        grades = school.block_set.all()
        classes = year.class_set.order_by('name')
        # query all necessary teacher to decrease hitting db time
        hometc_ids = [cl.teacher_id_id for cl in classes]
        teachers = Teacher.objects.filter(id__in=hometc_ids)
        hometc_dict = queryset_to_dict(teachers)
        # done teacher query
        # query aggregation to count number of students in classes
        # instead of counting on each class that hurts the db
        cl_ids = [cl.id for cl in classes]
        number_dict = {}
        numbers = Attend.objects.filter(is_member=True,_class__in=cl_ids)\
                .values('_class')\
                .annotate(number=Count('_class'))
        for n in numbers: number_dict[n['_class']] = n['number']
        # now we have dictionary number in the meaning of
        # {classid: number_of_student}
        uncs = UncategorizedClass.objects.filter(year_id=year)
        currentTerm = year.term_set.get(number=school.status)
        if currentTerm.number == 3:
            selected_term = Term.objects.get(year_id=currentTerm.year_id,
                    number=2)
        else:
            selected_term = currentTerm
        context = RequestContext(request)
        return render_to_response(SCHOOL,
                {'classes': classes,
                    'teachers': hometc_dict,
                    'numbers': number_dict,
                    'grades': grades,
                    'uncs': uncs,
                    'grades': grades,
                    'currentTerm':currentTerm,
                    'selected_term':selected_term,},
                context_instance=context)
    elif user_type == 'GIAO_VIEN':
        teaching_subjects = Subject.objects.\
                                    filter(teacher_id=user.teacher,
                                           class_id__year_id=year ).\
                                    order_by("class_id__block_id__number",
                                            "name")
        teaching_class = user.teacher.current_homeroom_class()
        term = get_current_term(request)
        if term.number == 3:
            term = Term.objects.get(year_id=term.year_id, number=2)

        head_subjects = None
        if teaching_class:
            head_subjects = Subject.objects.\
                                    filter(class_id=teaching_class).\
                                    order_by("index")
        return render_to_response(SCHOOL, {'teaching_subjects': teaching_subjects,
                                           'term': term,
                                           'teaching_class': teaching_class,
                                           'head_subjects': head_subjects},
                                  context_instance=RequestContext(request))
    elif user_type == 'HOC_SINH':
        return HttpResponseRedirect(reverse('student_detail', args=[user.pupil.id]))

def is_safe(school):
    if school.get_setting('class_labels'): return True
    else: return False

@need_login
@school_function
@operating_permission([u'HIEU_TRUONG', u'HIEU_PHO'])
def setup(request):
    message = None
    school = get_school(request)
    if request.is_ajax():
        if request.method == 'POST':
            data = None
            if 'update_school_detail' in request.POST:
                school_form = SchoolForm(request.POST, request=request)
                if school_form.is_valid():
                    school_form.save_to_model()
                    message = u'Bạn vừa cập nhật thông tin trường học thành công.\
                    Hãy cung cấp danh sách tên lớp học theo dạng [khối] [tên lớp]. Ví dụ: 10 A'

                data = simplejson.dumps({'message': message, 'status': 'done'})
            elif 'update_class_name' in request.POST:
                message, labels, success = parse_class_label(request, school)
                #print message, labels, success
                classes_ = None
                grades = None
                if success:
                    classes_ = school.get_setting('class_labels')
                    classes_ = '-'.join(classes_)
                    lower_bound = get_lower_bound(school)
                    upper_bound = get_upper_bound(school)
                    grades = '-'.join([str(grade) for grade in range(lower_bound, upper_bound)])

                data = simplejson.dumps({'message': message, 'status': success,
                                         'classes': classes_, 'grades': grades})

            elif 'start_year' in request.POST:
                if is_safe(school):
                    data = simplejson.dumps({'status': 'done'})
                else:
                    data = simplejson.dumps({'message': message, 'status': 'failed'})
            return HttpResponse(data, mimetype='json')
        else:
            raise Exception('StrangeRequestMethod')

    form_data = {'name': school.name, 'school_level': school.school_level,
                 'address': school.address, 'phone': school.phone,
                 'email': school.email}
    school_form = SchoolForm(form_data, request=request)
    message, labels, success = parse_class_label(request, school)

    if request.method == 'POST':
        school_form = SchoolForm(request.POST, request=request)
        if school_form.is_valid():
            school_form.save_to_model()
            message = u'Bạn vừa cập nhật thông tin trường học thành công. '

        if 'start_year' in request.POST and is_safe(school):
            HttpResponseRedirect(reverse('start_year'))

    context = RequestContext(request)
    return render_to_response(SETUP, {'form': school_form, 'message': message, 'labels': labels},
                              context_instance=context)

@need_login
def info(request):
    school = get_school(request)
    message = ''
    if request.method == 'POST':
        data = request.POST.copy()
        data['phone'] = data['phone'].strip()
        data['email'] = data['email'].strip()
        data['name'] = data['name'].strip()
        data['school_level'] = school.school_level
        data['lock_time'] = data['lock_time'].strip()
        data['class_labels'] = data['class_labels'].strip()
        data['semester_start_time'] = data['semester_start_time']
        data['semester_finish_time'] = data['semester_finish_time']
        name = ''
        address = ''
        email = ''
        phone = ''
        lock_time = ''
        class_labels = ''
        semester_finish_time = ''
        if request.is_ajax():
            form = SchoolForm(data, request=request)
            setting_form = SettingForm(data, request=request)
            if form.is_valid():
                form.save_to_model()
                message = u'Bạn vừa cập nhật thông tin trường học thành công'
                status = 'done'
            else:
                message = u'Có lỗi ở thông tin nhập vào'
                for a in form:
                    if a.name == 'phone':
                        if a.errors:
                            phone = str(a.errors)
                    elif a.name == 'email':
                        if a.errors:
                            email = str(a.errors)
                    elif a.name == 'address':
                        if a.errors:
                            address = str(a.errors)
                    elif a.name == 'name':
                        if a.errors:
                            name = str(a.errors)
                status = 'error'
            if setting_form.is_valid():
                setting_form.save_to_model()
                status += 'done'
            else:
                message = u'Có lỗi ở thông tin nhập vào'
                for a in setting_form:
                    if a.name == 'lock_time':
                        if a.errors:
                            lock_time = str(a.errors)
                    if a.name == 'semester_finish_time':
                        if a.errors:
                            semester_finish_time = str(a.errors)
                    elif a.name == 'class_labels':
                        if a.errors:
                            class_labels = str(a.errors)
                status += 'error'
            response = simplejson.dumps({'message': message,
                                         'status': status,
                                         'phone': phone,
                                         'email': email,
                                         'name': name,
                                         'address': address,
                                         'lock_time': lock_time,
                                         'semester_finish_time': semester_finish_time,
                                         'class_labels': class_labels})
            return HttpResponse(response, mimetype='json')

        form = SchoolForm(data, request=request)
        setting_form = SettingForm(data, request=request)
        if form.is_valid():
            form.save_to_model()
            return HttpResponseRedirect(reverse('info'))
    else:
        data = {'name': school.name,
                'address': school.address, 'phone': school.phone,
                'email': school.email, 'school_level': school.school_level,
                'allow_recover_password': school.allow_recover_password}
        form = SchoolForm(data, request=request)
        lock_time = school.get_setting('lock_time')
        labels = school.get_setting('class_labels')
        semester_start_time = school.get_setting('semester_start_time')
        semester_finish_time = school.get_setting('semester_finish_time')
        class_labels = ', '.join(labels)
        setting = {'lock_time': lock_time, 'class_labels': class_labels,
                   'semester_start_time': semester_start_time,
                   'semester_finish_time': semester_finish_time}
        setting_form = SettingForm(setting, request=request)

    context = RequestContext(request)
    return render_to_response(INFO, {'form': form,
                                     'school': school,
                                     'message': message,
                                     'setting_form': setting_form},
                              context_instance=context)


def empty(label_list):
    for l in label_list:
        if l.strip(): return False
    return True


# this following view handles all ajax request of indexing targets.
@transaction.commit_manually
def change_index(request, target, class_id=None):
    if target == u'subject': object = 'Subject'
    elif target == u'student': object = 'Pupil'
    elif target == u'teacher': object = 'Teacher'
    elif target == u'class': object = 'Class'
    else:
        raise Exception('BadTarget')
    if request.is_ajax():
        if request.method == 'POST':
            data = request.POST['data']
            try:
                list = data.split('/')
                for element in list:
                    if element:
                        #noinspection PyUnusedLocal
                        id = int(element.split('_')[0])
                        index = int(element.split('_')[1])
                        item = None
                        exec('item = ' + object + '.objects.get(id = id)')
                        #subject = Subject.objects.get(id = id)
                        if item.index != index:
                            item.index = index
                            item.save()
                transaction.commit()
                response = simplejson.dumps({'success': True})
                return HttpResponse(response, mimetype='json')
            except Exception as e:
                print e
    else:
        raise Exception('NotAjaxRequest')

@need_login
@operating_permission([u'HIEU_TRUONG', u'HIEU_PHO', u'GIAO_VIEN_CHU_NHIEM'])
def organize_students(request, class_id, type='0'):
    student_list = None
    _class = None
    _class = Class.objects.get(id=int(class_id))
    if type == '1':
        student_list = _class.students()
        student_list = multikeysort(student_list,
                ['real_first_name', 'family_name', 'middle_name', 'nick_name'])
    elif type == '2':
        student_list = _class.students()
        student_list = multikeysort(student_list,
                ['real_first_name', 'middle_name', 'family_name', 'nick_name'])
    else:
        student_list = _class.student_set.filter(attend__is_member=True)\
                .order_by('index').distinct()
    #if not gvcn(request, _class): return HttpResponseRedirect(reverse('school_index'))
    context = RequestContext(request)
    return render_to_response(ORGANIZE_STUDENTS,
            {'student_list': student_list, 'class': _class},
                              context_instance=context)


def parse_class_label(request, school):
    message = None
    if 'message' in request.session:
        message = request.session['message']
    labels = ','.join(school.get_setting('class_labels'))
    success = None
    if request.method == 'POST':
        labels = request.POST['labels']
        if u'Nhanh:' in labels or u'nhanh:' in labels:
            try:
                labels = labels.split(':')[1]
                labels = labels.strip()
            except Exception:
                pass
            if ',' in labels:
                list_labels = labels.split(',')
            else:
                list_labels = labels.split(' ')

            if empty(list_labels):
                message = u'Bạn cần nhập ít nhất một tên lớp.'
                success = False
            else:
                labels_to_save = []
                for label in list_labels:
                    if label:
                        label = label.strip()
                        for i in range(get_lower_bound(school), get_upper_bound(school)):
                            labels_to_save.append("%s %s" % (i, label))

                school.save_settings('class_labels', str(labels_to_save))
                message = u'Bạn vừa thiết lập thành công danh sách tên lớp cho trường.'
                success = True
            labels = 'Nhanh: ' + labels
        else:
            if ',' in labels:
                list_labels = labels.split(',')
                # draft version
                if not list_labels:
                    message = u'Bạn cần nhập ít nhất một tên lớp'
                    success = False
                else:
                    labels_to_save = []
                    for label in list_labels:
                        label = label.strip()
                        if label:
                            try:
                                grade = label.split(' ')[0]
                                grade = int(grade)
                                if get_lower_bound(school)<=grade<get_upper_bound(school):
                                    labels_to_save.append(label)
                            except Exception:
                                message = u'Các tên lớp phải được cung cấp theo dạng [khối][dấu cách][tên lớp]. Ví dụ: 10 A'
                                success = False
                                return message, labels, success
                    school.save_settings('class_labels', str(labels_to_save))
                    message = u'Bạn vừa thiết lập thành công danh sách tên lớp cho trường.'
                    success = True

    return message, labels, success

@transaction.commit_on_success
@need_login
@operating_permission([u'HIEU_TRUONG', u'HIEU_PHO'])
def class_label(request):
    school = get_school(request)
    message, labels, success = parse_class_label(request, school)

    t = loader.get_template(CLASS_LABEL)
    c = RequestContext(request, {'labels': labels, 'message': message}, )
    return HttpResponse(t.render(c))

@transaction.commit_on_success
@operating_permission([u'HIEU_TRUONG', u'HIEU_PHO'])
@school_function
@need_login
def b1(request):
    # tao moi cac khoi neu truong moi thanh lap
    school = get_school(request)
    loai_lop = school.get_setting('class_labels')
    if not loai_lop:
        message = u'Bạn chưa thiết lập danh sách tên lớp học cho nhà trường. Hãy điền vào ô dưới \
                    danh sách tên lớp học cho nhà trường rồi ấn nút Lưu lại'
        request.session['message'] = message
        transaction.commit()
        return HttpResponseRedirect(reverse('class_label'))
    if school.school_level == u'1':
        lower_bound = 1
        upper_bound = 5
        ds_mon_hoc = CAP1_DS_MON
    elif school.school_level == u'2':
        lower_bound = 6
        upper_bound = 9
        ds_mon_hoc = CAP2_DS_MON
    elif school.school_level == u'3':
        lower_bound = 10
        upper_bound = 12
        ds_mon_hoc = CAP3_DS_MON
    else:
        raise Exception('SchoolLevelInvalid')
    is_new_school = False
    is_new_year = False
    if not school.status:
        for khoi in range(lower_bound, upper_bound + 1):
            if not school.block_set.filter(number=khoi):
                block = Block()
                block.number = khoi
                block.school_id = school
                block.save()
        school.status = 1
        school.save()
        is_new_school = True
    elif school.status in [2,3]:
        school.status = 1
        school.save()
        is_new_year = True
    # tao nam hoc moi
    current_year = datetime.datetime.now().year
    if datetime.datetime.now().month < 5:
        current_year -= 1
    if is_new_school or is_new_year:
        # create new year
        year, temp = Year.objects.get_or_create(time=current_year,
                school_id=school)
        if not temp:  
            return HttpResponseRedirect(reverse("classes"))
        # create new StartYear
        sty, temp = StartYear.objects.get_or_create(time=current_year,
                school_id=school)
        # create new term
        for number in range(1,4):
            term, temp = Term.objects.get_or_create(number=number,
                    year_id=year)
            if number == 1:
                start_date = to_date(settings.TERM_START_DATE[number]
                        + str(current_year))
            else:
                start_date = to_date(settings.TERM_START_DATE[number]
                        + str(current_year + 1))
            finish_date = to_date(settings.TERM_FINISH_DATE[number]
                    + str(current_year + 1))
            term.start_date = start_date
            term.finish_date = finish_date
            term.save()

        # create new class.
        # -- tao cac lop ---
        for class_name in loai_lop:
            bl = school.block_set.get(number=int(class_name.split(' ')[0]))
            _class = Class.objects.create(name=class_name, status=1,
                                           block_id=bl, year_id=year)
            i = 0
            for mon in ds_mon_hoc:
                i += 1
                if mon in COMMENT_SUBJECT_LIST:
                    add_subject(subject_name=mon,
                        subject_type=mon,
                        nx=True,
                        _class=_class,
                        index=i)
                else:
                    add_subject(subject_name=mon, subject_type=mon,
                                _class=_class, index=i)
                    # -- day cac hoc sinh len lop
        last_year = school.year_set.filter(time__exact=current_year - 1)
        if last_year:
            blocks = school.block_set.all()
            for block in blocks:
                unc_class, temp = UncategorizedClass.objects.get_or_create(
                                    year_id = year,
                                    block_id = block,
                                    name = u'Phân lớp học sinh')
                if block.number == upper_bound:
                    classes = block.class_set.filter(year_id = last_year)
                    for _class in classes:
                        students = _class.students()
                        for student in students:
                            if student.tbnam_set.get(year_id=last_year).len_lop:
                                student.disable = False
                                student.graduate()
                                student.save()
                            else: # TRUONG HOP LUU BAN
                                student.unc_class_id = unc_class
                                student.learning_status = 'LB'
                                student.save()
                else:
                    classes = block.class_set.filter(year_id = last_year)
                    for _class in classes:
                        students = _class.students()
                        for student in students:
                            #TBNam.objects.create(student_id = student,
                            #                     year_id = year)
                            if student.tbnam_set.get(year_id=last_year).len_lop:
                                new_block = school.block_set.get(
                                                number=block.number + 1)
                                old_cn = student.class_id.name
                                new_cn = ' '.join([str(new_block.number),
                                                   old_cn.split()[1]])
                                try:
                                    new_class = new_block.class_set.get(
                                                    name=new_cn,
                                                    year_id=year)
                                    move_student(school, student, new_class)
                                except ObjectDoesNotExist:
                                    student.unc_class_id = unc_class
                                    student.learning_status = 'LL'
                                    student.save()
                            else: # TRUONG HOP LUU BAN
                                student.unc_class_id = unc_class
                                student.learning_status = 'LB'
                                student.save()
        else: # truong ko co nam cu
            pass
            # render HTML
    else:
    #raise Exception(u'Start_year: đã bắt đầu năm học rồi ?')
        pass
    return HttpResponseRedirect(reverse("classes"))


def years(request):
    school = get_school(request)
    years = school.year_set.all()
    return render_to_response(YEARS, {'years': years}, context_instance=RequestContext(request))


#@transaction.commit_on_success
#@need_login
#def classify(request):
#    try:
#        startyear = get_latest_startyear(request)
#        year = get_current_year(request)
#    except Exception as e:
#        print e
#        return HttpResponseRedirect(reverse("school_index"))
#
#    permission = get_permission(request)
#    if not permission in [u'HIEU_TRUONG', u'HIEU_PHO']:
#        return HttpResponseRedirect(reverse('school_index'))
#
#    message = None
#    nothing = False
#    student_list = startyear.pupil_set.filter(class_id__exact=None).order_by('first_name')
#    lower_bound = get_lower_bound(school)
#    grade = school.block_set.filter(number__exact=lower_bound)
#    _class_list = [(u'-1', u'Chọn lớp')]
#    class_list = year.class_set.filter(block_id__exact=grade)
#    for _class in class_list:
#        _class_list.append((_class.id, _class.name))
#    if request.method == "GET":
#        if not student_list:
#            message = u'Không còn học sinh nào cần được phân lớp.'
#            nothing = True
#    else:
#        form = ClassifyForm(request.POST, student_list=student_list, class_list=_class_list)
#        if form.is_valid():
#            count = 0
#            for student in student_list:
#                _class = form.cleaned_data[str(student.id)]
#                if _class == u'-1':
#                    _class = None
#                    student.class_id = _class
#                    student.save()
#
#                else:
#                    _class = year.class_set.get(id=int(_class))
#                    move_student(school, student, _class)
#                    count += 1
#            message = u'Bạn vừa phân lớp thành công cho ' + str(count) + u' học sinh.'
#        else:
#            message = u'Xảy ra trục trặc trong quá trình nhập dữ liệu.'
#        student_list = startyear.pupil_set.filter(class_id__exact=None).order_by('first_name')
#    form = ClassifyForm(student_list=student_list, class_list=_class_list)
#    return render_to_response(CLASSIFY,
#            {'message': message, 'student_list': student_list, 'form': form, 'nothing': nothing},
#                              context_instance=RequestContext(request))



@need_login
def password_change(request):
    user = request.user
    form = PasswordChangeForm(user)
    message = ''
    if request.method == 'POST':
        form = PasswordChangeForm(user, request.POST)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('change_success'))
    t = loader.get_template(os.path.join('school', 'password_change.html'))
    c = RequestContext(request, {'form': form, 'message': message})
    return HttpResponse(t.render(c))

def change_success(request):
    logout(request)
    t = loader.get_template(os.path.join('school','cps.html'))
    c = RequestContext(request)
    return HttpResponse(t.render(c))

@need_login
def username_change(request):
    user = request.user
    form = UsernameChangeForm(user)
    message = ''
    if request.method == 'POST':
        form = UsernameChangeForm(user, request.POST)
        if form.is_valid() and user.userprofile.username_change == 0:
            form.save()
            return HttpResponseRedirect(reverse('change_success'))
    t = loader.get_template(os.path.join('school', 'username_change.html'))
    c = RequestContext(request, {'form': form, 'message': message})
    return HttpResponse(t.render(c))

@need_login
@operating_permission([u'HIEU_TRUONG', u'HIEU_PHO'])
def student_account(request, student_id):
    user = request.user
    message = ''
    student = user.userprofile.organization.pupil_set.get(id=student_id)
    url = reverse('student_account',args=[student_id])
    if request.method == 'POST':
        if student.sms_phone or student.email:
            new_password, raw_password = make_default_password()
            student.user_id.set_password(new_password)
            student.user_id.is_active = True
            student.user_id.save()
            content = u'Tài khoản Trường Nhà của bạn đã được đổi.\n' +\
                      u'Tên đăng nhập: ' +\
                      student.user_id.username + u'\nMật khẩu: ' + raw_password
            if student.email:
                subject = u'Thông báo thay đổi mật khẩu'
                send_email(subject,content,to_addr=[student.email])
            if student.sms_phone:
                try:
                    sendSMS(student.sms_phone,to_en1(content),user)
                except Exception as e:
                    print e
                    pass
                    #TODO: notice user about this exception
            message = u'Mật khẩu của học sinh đã được tạo lại và gửi vào số điện thoại và email đã đăng ký'
        else:
            message = u'Học sinh chưa đăng ký số điện thoại hoặc email nên không cấp lại được mật khẩu'
        data = simplejson.dumps({'message': message})
        return HttpResponse(data, mimetype='json')
    t = loader.get_template(os.path.join('school', 'account.html'))
    c = RequestContext(request, {'account': student.user_id.username, 'url': url, 'message': message})
    return HttpResponse(t.render(c))

#@need_login
#@operating_permission(['HIEU_TRUONG', 'HIEU_PHO'])
#def teacher_account(request, teacher_id):
#    user = request.user
#    message = ''
#    teacher = user.userprofile.organization.teacher_set.get(id=teacher_id)
#    url = reverse('teacher_account', args=[teacher_id])
#    if request.method == 'POST':
#        if teacher.sms_phone or teacher.email:
#            new_password, raw_password = make_default_password()
#            teacher.user_id.password = new_password
#            teacher.user_id.is_active = True
#            content = u'Mật khẩu của bạn tại hệ thống Trường Nhà đã được thay đổi.\n' +\
#                      u'Sử dụng thông tin dưới đây để đăng nhập.\n' + u'Tên đăng nhập: ' +\
#                      teacher.user_id.username + u'\nMật khẩu: ' + raw_password
#            if teacher.sms_phone:
#                try:
#                    sendSMS(teacher.sms_phone,to_en1(content),user, save_to_db=False)
#                    message = u'Mật khẩu của giáo viên đã được tạo lại và gửi vào số điện thoại nhắn tin đã đăng ký'
#                    teacher.user_id.save()
#                except Exception as e:
#                    print e
#                    message = u'Không thể gửi tin nhắn tới số ' + teacher.sms_phone + u'.'
#                    if teacher.email:
#                        try:
#                            subject = u'Thông báo thay đổi mật khẩu'
#                            send_email(subject,content, to_addr=[teacher.email])
#                            message = u'Mật khẩu của giáo viên đã được tạo lại và gửi vào địa chỉ email đã đăng ký'
#                            teacher.user_id.save()
#                        except Exception as e:
#                            print e
#                            message += u'Không thể gửi email tới địa chỉ ' + teacher.email + u'.'
#            if not teacher.sms_phone and not teacher.email:
#                message = u'Để thay đổi mật khẩu, tài khoản phải có địa chỉ email hoặc số điện thoại nhắn tin'
#        else:
#            message = u'Giáo viên chưa đăng ký số điện thoại hoặc email nên không cấp lại được mật khẩu'
#        data = simplejson.dumps({'message': message})
#        return HttpResponse(data, mimetype='json')
#    t = loader.get_template(os.path.join('school', 'account.html'))
#    c = RequestContext(request, {'account': teacher.user_id.username, 'url': url, 'message': message})
#    return HttpResponse(t.render(c))


#User: loi.luuthe@gmail.com
#This function receives a form from template, and immediately creates new class with from the form information

#@need_login
#@school_function
#def student(request, student_id):
#    school = get_school(request)
#    if not request.is_ajax():
#        raise Exception("PageDoesNotExist")
#    try:
#        student = Pupil.objects.get(id=student_id)
#        if school != student.get_school():
#            raise Exception("IllegalAccess")
#        return render_to_response(STUDENT, {'student': student}, context_instance=RequestContext(request))
#    except ObjectDoesNotExist as e:
#                raise Exception("StudentDoesNotExist")


#sort_type = '1': fullname, '2': birthday, '3':'sex'
#sort_status = '0':ac '1':'dec

#def team(request, team_id, sort_type=1, sort_status=0):
#    user = request.user
#    if not user.is_authenticated():
#        return HttpResponseRedirect(reverse('login'))
#    try:
#        school = get_school(request)
#    except Exception:
#        return HttpResponseRedirect(reverse('index'))
#    pos = get_position(request)
#    if request.method == 'POST' and request.is_ajax() and pos > 3:
#        try:
#            if request.POST['request_type'] == u'addGroup':
#                try:
#                    g = Group.objects.get(name=request.POST['name'].strip(), team_id=request.POST['team_id'])
#                    message = u'Nhóm này đã tồn tại'
#                    data = simplejson.dumps({'message': message})
#                    return HttpResponse(data, mimetype='json')
#                except ObjectDoesNotExist:
#                    data = {'name': request.POST['name'].strip(), 'team_id': request.POST['team_id']}
#                    t = GroupForm(data, school=school)
#                    if t.is_valid():
#                        t.save()
#                    else:
#                        raise Exception('AddGroupException')
#                    return HttpResponseRedirect('/school/team/' + request.POST['team_id'])
#            if request.POST['request_type'] == u'renameGroup':
#                g = Group.objects.get(id=request.POST['id'])
#                try:
#                    _t = g.team_id.group_set.get(name=request.POST['name'])
#                    message = u'Nhóm này đã tồn tại'
#                    data = simplejson.dumps({'message': message})
#                    return HttpResponse(data, mimetype='json')
#                except ObjectDoesNotExist:
#                    g.name = request.POST['name'].strip()
#                    g.save()
#                    return HttpResponseRedirect('/school/team/' + team_id)
#        except Exception as e:
#            print e
#            pass
#    team = school.team_set.get(id=team_id)
#    groupList = team.group_set.all()
#    t = loader.get_template(os.path.join('school', 'team.html'))
#
#    c = RequestContext(request, {'groupList': groupList,
#                                 'team': team,
#                                 'pos': pos,
#                                 'sort_type': sort_type,
#                                 'sort_status': sort_status,
#                                 'next_status': 1 - int(sort_status),
#                                 })
#    return HttpResponse(t.render(c))
#
#@need_login
#@school_function
#def teachers_tab(request, sort_type=1, sort_status=0):
#    school = get_school(request)
#    pos = get_position(request)
#    message = None
#    form = TeacherForm(school.id)
#    if request.is_ajax() and pos > 3:
#        if request.method == 'POST' and request.POST['request_type'] == u'team':
#            try:
#                t = school.teacher_set.get(id=request.POST['id'])
#                if request.POST['team']:
#
#                    team = school.team_set.get(id=request.POST['team'])
#                else:
#                    team = None
#                t.team_id = team
#                t.group_id = None
#                t.save()
#                response = simplejson.dumps({'success': True})
#                return HttpResponse(response, mimetype='json')
#            except Exception as e:
#                print e
#        elif request.method == 'POST' and request.POST['request_type'] == u'major':
#            try:
#                t = school.teacher_set.get(id=request.POST['id'])
#                major = request.POST['major']
#                t.major = major
#                t.save()
#                response = simplejson.dumps({'success': True})
#                return HttpResponse(response, mimetype='json')
#            except Exception as e:
#                print e
#        elif request.method == 'POST' and request.POST['request_type'] == u'add':
#            if request.POST['first_name'].strip():
#                name = request.POST['first_name'].split()
#                last_name = ' '.join(name[:len(name) - 1])
#                first_name = name[len(name) - 1]
#            else:
#                last_name = ''
#                first_name = ''
#            index = school.teacher_set.count() + 1
#            teamlist = request.POST.getlist('team_id')
#            tid = teamlist.pop()
#            if tid != u'':
#                team = school.team_set.get(id=tid)
#                team_id = team.id
#            else:
#                team = None
#                team_id = ''
#            data = {'first_name': first_name, 'last_name': last_name, 'birthday': request.POST['birthday'],
#                    'sex': request.POST['sex'], 'school_id': school.id,
#                    'team_id': team_id, 'major': request.POST['major'], 'index': index}
#            form = TeacherForm(school.id, data)
#            if form.is_valid():
#                birthday = to_date(request.POST['birthday'])
#                try:
#                    test = school.teacher_set.get(first_name__exact=data['first_name'],
#                                                  last_name__exact=data['last_name'], birthday__exact=birthday)
#                    message = u'Giáo viên này đã tồn tại trong hệ thống'
#                except ObjectDoesNotExist:
#                    add_teacher(first_name=data['first_name'], last_name=data['last_name'], school=get_school(request),
#                                birthday=birthday,
#                                sex=data['sex'],team_id=team, major=data['major'])
#                    message = u'Bạn vừa thêm một giáo viên mới'
#                form = TeacherForm(school.id)
#            else:
#                if data['first_name'] != '':
#                    data['first_name'] = data['last_name'] + ' ' + data['first_name']
#                    form = TeacherForm(school.id, data)
#
#    if int(sort_type) == 1:
#        if not int(sort_status):
#            teacherList = school.teacher_set.order_by('first_name', 'last_name')
#        else:
#            teacherList = school.teacher_set.order_by('-first_name', '-last_name')
#    if int(sort_type) == 2:
#        if not int(sort_status):
#            teacherList = school.teacher_set.order_by('birthday')
#        else:
#            teacherList = school.teacher_set.order_by('-birthday')
#    if int(sort_type) == 3:
#        if not int(sort_status):
#            teacherList = school.teacher_set.order_by('sex')
#        else:
#            teacherList = school.teacher_set.order_by('-sex')
#    if int(sort_type) == 4:
#        if not int(sort_status):
#            teacherList = school.teacher_set.order_by('team_id')
#        else:
#            teacherList = school.teacher_set.order_by('-team_id')
#
#    flist = []
#    i = 0
#    for t in teacherList:
#        flist.append(TeacherForm(school.id))
#        flist[i] = TeacherForm(school.id, instance=t)
#        i += 1
#    list = zip(teacherList, flist)
#    t = loader.get_template(os.path.join('school', 'teachers_tab.html'))
#    tmp = get_teacher(request)
#    id = 0
#    if tmp:
#        id = tmp.id
#    c = RequestContext(request, {'form': form,
#                                 'message': message,
#                                 'list': list,
#                                 'sort_type': sort_type,
#                                 'sort_status': sort_status,
#                                 'next_status': 1 - int(sort_status),
#                                 'pos': pos,
#                                 'teacher_id': id})
#    return HttpResponse(t.render(c))

def date_check(request):
    if request.is_ajax() and request.method == 'POST':
        try:
            date = to_date(request.POST['date'])
        except Exception:
            data = simplejson.dumps({'status':'false'})
            return HttpResponse(data, mimetype='json')
    data = simplejson.dumps({'date': request.POST['date'],'status':'true'})
    return HttpResponse(data, mimetype='json')

@need_login
def diem_danh_form(request, class_id):
    day = int(date.today().day)
    month = int(date.today().month)
    year = int(date.today().year)
    url = reverse('dd',args=[str(class_id),str(day),str(month),str(year)])
    return HttpResponseRedirect(url)


#def tnc_select(request):
#    user = request.user
#    if not user.is_authenticated():
#        return HttpResponseRedirect(reverse('login'))
#    y = get_current_year(request)
#    year_id = y.id
#    pos = get_position(request)
#    if pos < 2 and pos != 3:
#        return HttpResponseRedirect(reverse('index'))
#    elif pos == 3:
#        try:
#            tc = y.class_set.get(teacher_id__exact=request.user.teacher.id)
#            url = '/school/diemdanh/' + str(tc.id) + '/' + str(date.today().day) + '/' + str(
#                date.today().month) + '/' + str(date.today().year)
#            return HttpResponseRedirect(url)
#        except ObjectDoesNotExist:
#            return HttpResponseRedirect(reverse('index'))
#    message = u'Hãy chọn ngày và lớp học bạn muốn điểm danh'
#    form = DateAndClassForm(year_id)
#    if request.method == 'POST':
#        form = DateAndClassForm(year_id, request.POST)
#        if form.is_valid():
#            d = to_date(request.POST['date'])
#            class_id = str(request.POST['class_id'])
#            day = d.day
#            month = d.month
#            year = d.year
#            url = '/school/diemdanh/' + class_id + '/' + str(day) + '/' + str(month) + '/' + str(year)
#            return HttpResponseRedirect(url)
#        else:
#            message = u'Chọn lớp và ngày chưa đúng.'
#    t = loader.get_template(os.path.join('school', 'time_class_select.html'))
#    c = RequestContext(request, {'form': form, 'message': message})
#    return HttpResponse(t.render(c))

def tk_dd_lop(class_id, term_id):
    ppl = Pupil.objects.filter(class_id=class_id)
    for p in ppl:
        tk_diem_danh(p.id, term_id)


def tk_diem_danh(student_id, term_id):
    pupil = Pupil.objects.get(id=student_id)
    ts = DiemDanh.objects.filter(student_id=student_id, term_id=term_id).count()
    cp = DiemDanh.objects.filter(student_id=student_id, term_id=term_id, loai=u'C').count()
    kp = ts - cp
    data = {'student_id': student_id, 'tong_so': ts, 'co_phep': cp, 'khong_phep': kp, 'term_id': term_id}
    tk = TKDiemDanhForm()
    try:
        tkdd = TKDiemDanh.objects.get(student_id__exact=student_id, term_id__exact=term_id)
        tk = TKDiemDanhForm(data, instance=tkdd)
    except ObjectDoesNotExist:
        tk = TKDiemDanhForm(data)
    tk.save()


#def test(request):
#    form = PupilForm()
#    message = 'Hello'
#    t = loader.get_template('school/diem_danh_form.html')
#    c = RequestContext(request, {'form': form, 'message': message})
#
#    return HttpResponse(t.render(c))

@need_login
@school_function
def deleteClass(request, class_id):
    try:
        s = get_current_year(request).class_set.get(id=class_id)
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('classes'))
    if not in_school(request, s.block_id.school_id):
        return HttpResponseRedirect(reverse('index'))
    if get_position(request) < 4:
        return HttpResponseRedirect(reverse('school_index'))
    if s.number_of_pupils() > 0:
        return HttpResponseNotAllowed('Not Empty Class')
    if s.id in settings.PREVENTED_CLASSES:
        return HttpResponseNotAllowed('PreventedClass')
    s.delete()
    return HttpResponse('OK')


@need_login
@school_function
def deleteStudentInSchool(request, student_id):
    sub = Pupil.objects.get(id=student_id)
    if not in_school(request, sub.current_class().block_id.school_id):
        return HttpResponseRedirect(reverse('index'))
    if get_position(request) < 4:
        return HttpResponseRedirect(reverse('index'))
    sub.delete()
    return HttpResponseRedirect('/school/students')

@need_login
def timeTable(request, class_id):
    user = request.user
    pos = get_position(request)
    school = get_school(request)
    if pos < 1:
        return HttpResponseRedirect(reverse('index'))
    if pos == 1 and inClass(request, class_id) == 0:
        return HttpResponseRedirect(reverse('index'))
    sync_tkb_db(request)
    cl = Class.objects.get(id=class_id)
    if not in_school(request, cl.block_id.school_id):
        return HttpResponseRedirect(reverse('index'))

    if user.userprofile.organization.level == 'S':
        year = cl.year_id
    else:
        year = get_current_year(request)
    classList = Class.objects.filter(year_id=year).order_by('name')
    for d in range(2, 8):
        try:
            tmp = cl.tkb_set.get(day=d)
        except Exception as e:
            t = TKB()
            t.day = d
            t.class_id = cl
            t.save()

    if request.method == "POST":
        if request.is_ajax():
            try:
                d = int(request.POST['day'])
                t = cl.tkb_set.get(day=d)
                if not t:
                    raise Exception('StrangeRequestMethod')
                request_type = request.POST['request_type'].strip()
                if not (request_type in ['period_' + str(i) for i in range(1, 11)]):
                    raise Exception('StrangeRequestMethod')
                if request.POST['sub']:
                    if request.POST['sub'] == u'-1':
                        setattr(t, request_type, None)
                        if getattr(t, 'sinhhoat') == int(request_type.split("_")[1]):
                            setattr(t, 'sinhhoat', None)
                        setattr(t, 'chaoco', int(request_type.split("_")[1]))
                    elif request.POST['sub'] == u'-2':
                        setattr(t, request_type, None)
                        if getattr(t, 'chaoco') == int(request_type.split("_")[1]):
                            setattr(t, 'chaoco', None)
                        setattr(t, 'sinhhoat', int(request_type.split("_")[1]))
                    else:
                        if getattr(t, 'sinhhoat') == int(request_type.split("_")[1]):
                            setattr(t, 'sinhhoat', None)
                        if getattr(t, 'chaoco') == int(request_type.split("_")[1]):
                            setattr(t, 'chaoco', None)
                        sub = cl.subject_set.get(id = int(request.POST['sub']))
                        setattr(t, request_type, sub)
                else:
                    setattr(t, request_type, None)
                    if getattr(t, 'sinhhoat') == int(request_type.split("_")[1]):
                        setattr(t, 'sinhhoat', None)
                    if getattr(t, 'chaoco') == int(request_type.split("_")[1]):
                        setattr(t, 'chaoco', None)
                t.save()
            except Exception as e:
                message = u"Có lỗi xảy ra."
                print e
                data = simplejson.dumps({'message': message})
                return HttpResponse(data, mimetype='json')

            message = u"Thời khóa biểu thay đổi thành công."
            data = simplejson.dumps({'message': message})
            return HttpResponse(data, mimetype='json')
        else:
            try:
                for d in range(2, 8):
                    t = cl.tkb_set.get(day=d)
                    for i in range(1, 11):
                        plist = request.POST.getlist('period_' + str(i))
                        if plist[d-2]:
                            if plist[d-2] == -1:
                                setattr(t, 'period_' + str(i), None)
                                setattr(t, 'chaoco', i)
                            elif plist[d-2] == -2:
                                setattr(t, 'period_' + str(i), None)
                                setattr(t, 'sinhhoat', i)
                            else:
                                if getattr(t, 'chaoco') == i:
                                    setattr(t, 'chaoco', None)
                                if getattr(t, 'sinhhoat') == i:
                                    setattr(t, 'sinhhoat', None)
                                setattr(t, 'period_' + str(i), Subject.objects.get(id=int(plist[d - 2])))
                        else:
                            setattr(t, 'period_' + str(i), None)
                            if getattr(t, 'chaoco') == i:
                                setattr(t, 'chaoco', None)
                            if getattr(t, 'sinhhoat') == i:
                                setattr(t, 'sinhhoat', None)
                        t.save()
            except Exception as e:
                print e
    timeTables = TKB.objects.filter(class_id=class_id).order_by('day')
    subject = cl.subject_set.all()
    number_of_periods = {}
    for sub in subject:
        number_of_periods[sub.name] = 0
    for ilesson in timeTables:
        for i in range(1, 11):
            subject_name = getattr(ilesson, 'period_'+str(i))
            if subject_name is not None:
                number_of_periods[subject_name.name]+=1

    TKBForms = []
    for t in timeTables:
        TKBForms.append(TKBForm(class_id, instance=t))
    lesson = []
    week = []
    for d in range(1, 11):
        lesson.append(d)
    for w in range(2, 8):
        week.append(w)

    #find chaoco and sinhhoat lists
    chaoco_list = cl.tkb_set.filter(chaoco__isnull=False)
    sinhhoat_list = cl.tkb_set.filter(sinhhoat__isnull=False)
    cc = []
    sh = []
    for i in chaoco_list:
        cc.append(int(i.day*10 + int(i.chaoco)))
    for i in sinhhoat_list:
        sh.append(int(i.day*10 + i.sinhhoat))
    list = zip(timeTables, TKBForms)
    t = loader.get_template(os.path.join('school', 'time_table.html'))
    c = RequestContext(request, {'list': list,
                                 'subject': subject,
                                 'lesson': lesson,
                                 'week': week,
                                 'pos': get_position(request),
                                 'classList': classList,
                                 'class': cl,
                                 'no_periods' : number_of_periods,
                                 'chaoco_list': cc,
                                 'sinhhoat_list': sh,
                                 })
    return HttpResponse(t.render(c))

@need_login
def timeTable_school(request):
    pos = get_position(request)
    school = get_school(request)
    if pos < 1:
        return HttpResponseRedirect(reverse('index'))

    year = get_current_year(request)
    sync_tkb_db(request)
    classList = year.class_set.all().order_by('name')
    table = []
    for cl in classList:
        tcl = cl.tkb_set.all()
        if not (tcl.count() == 6):
            for d in range(2, 8):
                try:
                    tmp = cl.tkb_set.get(day=d)
                except Exception as e:
                    t = TKB()
                    t.day = d
                    t.class_id = cl
                    t.save()
        tcl = cl.tkb_set.all()
        table.append(tcl)

    lesson = []
    week = []
    for d in range(1, 11):
        lesson.append(d)
    for w in range(2, 8):
        week.append(w)
    list = zip(classList, table)
    sinhhoat = []
    chaoco=[]
    for cl in classList:
        chaoco_list = cl.tkb_set.filter(chaoco__isnull=False)
        sinhhoat_list = cl.tkb_set.filter(sinhhoat__isnull=False)
        for i in chaoco_list:
            chaoco.append(cl.id*100 + int(i.day*10 + int(i.chaoco)))
        for i in sinhhoat_list:
            sinhhoat.append(cl.id*100 + int(i.day*10 + int(i.sinhhoat)))

    t = loader.get_template(os.path.join('school', 'time_table_school.html'))
    c = RequestContext(request, {'list': list,
                                 'pos': get_position(request),
                                 'lesson': lesson,
                                 'week': week,
                                 'classList': classList,
                                 'chaoco' : chaoco,
                                 'sinhhoat' : sinhhoat,
                                 })
    return HttpResponse(t.render(c))

@need_login
def subjectAgenda(request, subject_id):
    school = get_school(request)
    pos = get_position(request)
    sub = Subject.objects.get(id=subject_id)
    if get_teacher(request) == sub.teacher_id:
        pos = 4
    lessList = sub.lesson_set.all().order_by("index")
    #get the subject list of school
    
    sub_index = -1
    for item in SUBJECT_CHOICES:
        if item[1] == sub.type:
            sub_index = item[0]
            break
    term = get_current_term(request)
    grade = sub.class_id.block_id.number
    school = get_school(request)
    if len(lessList) == 0 or lessList is None:
        lessSchool = SchoolLesson.objects.filter(school = school.id, term = term.number, subject = sub_index, grade = grade)
        if lessSchool is not None:
            for iless in lessSchool:
                less = Lesson()
                less.index = iless.index
                less.subject_id = sub
                less.note = iless.note
                less.title = iless.title
                less.save()
        lessList = sub.lesson_set.all().order_by("index")
    if len(lessList) == 0 or lessList is None:
        lessSystem = SystemLesson.objects.filter(term = term.number, subject = sub_index, grade = grade)
        if lessSystem is not None:
            for iless in lessSystem:
                less = Lesson()
                less.index = iless.index
                less.subject_id = sub
                less.note = iless.note
                less.title = iless.title
                less.save()
                
    lessList = sub.lesson_set.all().order_by("index")
    lessForm = []
    for i in lessList:
        newForm = LessonForm(instance=i)
        lessForm.append(newForm)
    list = zip(lessList, lessForm)
    message = u''
    if request.is_ajax():
        if request.POST['request_type'] != 'delete':
            val = request.POST['value']
            _id = int(request.POST['id'])
            less = sub.lesson_set.get(id=_id)
            setattr(less, request.POST['request_type'], val)
            less.save()
            message = u'Đã lưu'
            data = simplejson.dumps({'message': message})
            return HttpResponse(data, mimetype='json')
        elif request.POST['request_type'] == 'delete':
            _id = int(request.POST['id'])
            less = sub.lesson_set.get(id=_id)
            less.delete()
            message = u'Đã xóa'
            data = simplejson.dumps({'message': message})
            return HttpResponse(data, mimetype='json')
    elif request.method == 'POST' and pos > 3:
        title_list = request.POST.getlist('title')
        note_list = request.POST.getlist('note')
        lessonList = sub.lesson_set.all()
        i = 0
        for s in lessonList:
            data = {'index' : s.index, 'subject_id': s.subject_id.id,'title':title_list[i], 'note':note_list[i]}
            of = lessForm[i]
            lessForm[i] = LessonForm(data, instance=s)
            if str(of) != str(lessForm[i]):
                if lessForm[i].is_valid():
                    lessForm[i].save()
                    message = 'Danh sách đã được cập nhật.'
            i += 1

    t = loader.get_template(os.path.join('school', 'subject_agenda.html'))
    c = RequestContext(request, {'list': list,
                                 'pos': pos,
                                 'class': sub.class_id,
                                 'sub': sub,
                                 'term' : term.number,
                                 'grade' : grade,
                                 'index' : sub_index,
                                 'message': message
                                 })
    return HttpResponse(t.render(c))

@need_login
def timetableTeacher(request):
    pos = get_position(request)
    year = get_current_year(request)
    tc = get_teacher(request)

    if not tc:
        return HttpResponseRedirect(reverse('index'))
    sync_tkb_db(request)
    subjectList = tc.subject_set.all()
    table = {}
    for day in range(2, 8):
            table[day] = {}
            for nless in range (1, 11):
                table[day][nless]=[]

    for sub in subjectList:
        cl = sub.class_id
        if not cl.year_id.id == year.id:
            continue
        for d in range(2, 8):
            try:
                tkbs = cl.tkb_set.get(day= d)
            except ObjectDoesNotExist:
                tkbs = TKB()
                tkbs.day = d
                tkbs.class_id = cl
                tkbs.save()
            nums = tkbs.get_numbers(sub)
            if not len(nums): continue
            for num in nums:
                table[d][num].append(sub)

    tp = loader.get_template(os.path.join('school', 'timetableTeacher.html'))
    c = RequestContext(request, {'table': table,
                                 'pos': pos,
                                 'teacher': tc,
                                 })
    return HttpResponse(tp.render(c))

@need_login
def donvi(request):
    try:
        so = request.user.userprofile.organization
    except Exception as e:
        return HttpResponseRedirect(reverse('index'))
    if so.level != 'S':
        return HttpResponseRedirect(reverse('index'))
    try:
        del request.session['school_id']
    except Exception:
        pass
    listdonvi = so.organization_set.all().order_by("name")
    t = loader.get_template(os.path.join('school','donvi.html'))
    c = RequestContext( request, {'list':listdonvi})
    return HttpResponse(t.render(c))

@need_login
def ssv(request,school_id):
    try:
        so = request.user.userprofile.organization
    except Exception as e:
        return HttpResponseRedirect(reverse('index'))
    if so.level != 'S':
        return HttpResponseRedirect(reverse('index'))
    request.session['school_id'] = school_id
    school = so.organization_set.get(id = school_id)
    year = get_current_year(request)
    grades = school.block_set.all()
    classes = year.class_set.order_by('name')
    # query all necessary teacher to decrease hitting db time
    hometc_ids = [cl.teacher_id_id for cl in classes]
    teachers = Teacher.objects.filter(id__in=hometc_ids)
    hometc_dict = queryset_to_dict(teachers)
    # done teacher query
    # query aggregation to count number of students in classes
    # instead of counting on each class that hurts the db
    cl_ids = [cl.id for cl in classes]
    number_dict = {}
    numbers = Attend.objects.filter(is_member=True,_class__in=cl_ids)\
    .values('_class')\
    .annotate(number=Count('_class'))
    for n in numbers: number_dict[n['_class']] = n['number']
    # now we have dictionary number in the meaning of
    # {classid: number_of_student}
    uncs = UncategorizedClass.objects.filter(year_id=year)
    currentTerm = year.term_set.get(number=school.status)
    if currentTerm.number == 3:
        selected_term = Term.objects.get(year_id=currentTerm.year_id,
            number=2)
    else:
        selected_term = currentTerm
    context = RequestContext(request)
    return render_to_response(SCHOOL,
        {'classes': classes,
         'teachers': hometc_dict,
         'numbers': number_dict,
         'grades': grades,
         'uncs': uncs,
         'grades': grades,
         'currentTerm':currentTerm,
         'selected_term':selected_term,},
        context_instance=context)

@need_login
@school_function
@year_started
@operating_permission(['HIEU_TRUONG', 'HIEU_PHO'])
def school_subject_agenda(request, subject = 1, grade = 6, term = 1):
    school = get_school(request)
    lessons = ''
    cap = int(school.school_level)
    if cap == 3:
        data = {'subject': subject, 'grade': 10, 'term': term}
        grade = 10
        form = SelectSchoolLessonForm3(data)
    elif cap == 2:
        data = {'subject': subject, 'grade': grade, 'term': term}
        form = SelectSchoolLessonForm2(data)
    else:
        return

    if request.method == 'POST':
        if cap == 3:
            form = SelectSchoolLessonForm3(request.POST)
        elif cap == 2:
            form = SelectSchoolLessonForm2(request.POST)

        subject= int(request.POST['subject'])
        grade=int(request.POST['grade'])
        term=int(request.POST['term'])
    try:
        lessons = SchoolLesson.objects.filter(school = school.id, subject=subject, grade=grade, term=term)
    except  Exception as ex:
        lessons = None
    #if lessons is None, get the Lessons of System
    if lessons is  None or len(lessons) == 0:
        syslessons = SystemLesson.objects.filter(subject=subject, grade=grade, term=term)
        if syslessons is not None:
            for iLessons in syslessons:
                less = SchoolLesson()
                less.school = school
                less.index = iLessons.index
                less.subject = subject
                less.grade = grade
                less.title = iLessons.title
                less.note = iLessons.note
                less.term = term
                less.save()
            lessons = SchoolLesson.objects.filter(subject=subject, grade=grade, term=term, school = school.id)

    c = RequestContext(request,
            {'list': lessons, 'id': subject, 'subject': SUBJECT_CHOICES[int(subject) - 1][1], 'grade': grade,
             'term': term, 'form': form, 'school' : school})
    t = loader.get_template(os.path.join('school', 'manage_school_agenda.html'))
    return HttpResponse(t.render(c))

@need_login
def use_school_agenda(request, subject_id):
    school = get_school(request)
    if not school.status:
        return HttpResponseRedirect(reverse('setup'))
    try:
        year = get_current_year(request)
        sub = Subject.objects.get(id=subject_id)
    except Exception:
        return HttpResponseRedirect(reverse('setup'))
    
    pos = get_position(request)
    if get_teacher(request) == sub.teacher_id:
        pos = 4
    if pos < 4:
        return HttpResponseRedirect(reverse('index'))
    sub_index = None
    for item in SUBJECT_CHOICES:
        if item[1] == sub.type:
            sub_index = item[0]
            break
    term = get_current_term(request)
    grade = sub.class_id.block_id.number
    if request.method == 'POST':
        lessons = sub.lesson_set.all()
        if lessons is not None and len(lessons) > 0:
            for less in lessons:
                less.delete()
        lessSystem = SchoolLesson.objects.filter(subject=sub_index, grade=grade, term=term.number, school = school.id)
        if lessSystem is not None:
            for iless in lessSystem:
                less = Lesson()
                less.index = iless.index
                less.subject_id = sub
                less.note = iless.note
                less.title = iless.title
                less.save()
        return HttpResponseRedirect(reverse('subject_agenda',args=[int(sub.id)]))
    try:
        lessons = SchoolLesson.objects.filter(subject=sub_index, grade=grade, term=term.number, school = school.id)
    except  Exception as ex:
        lessons = None
    c = RequestContext(request,{'list': lessons, 'sub' : sub, 'grade' : grade})
    t = loader.get_template(os.path.join('school', 'use_school_agenda.html'))
    return HttpResponse(t.render(c))

@need_login
def use_system_agenda(request, subject_id):
    school = get_school(request)
    if not school.status:
        return HttpResponseRedirect(reverse('setup'))
    try:
        sub = Subject.objects.get(id=subject_id)
    except Exception:
        return HttpResponseRedirect(reverse('setup'))

    pos = get_position(request)
    if get_teacher(request) == sub.teacher_id:
        pos = 4
    if pos < 4:
        return HttpResponseRedirect(reverse('index'))
    sub_index = None
    for item in SUBJECT_CHOICES:
        if item[1] == sub.type:
            sub_index = item[0]
            break
    term = get_current_term(request)
    grade = sub.class_id.block_id.number
    if request.method == 'POST':
        lessons = sub.lesson_set.all()
        if lessons is not None and len(lessons) > 0:
            for less in lessons:
                less.delete()
        lessSystem = SystemLesson.objects.filter(subject=sub_index, grade=grade, term=term.number)
        if lessSystem is not None:
            for iless in lessSystem:
                less = Lesson()
                less.index = iless.index
                less.subject_id = sub
                less.note = iless.note
                less.title = iless.title
                less.save()
        return HttpResponseRedirect(reverse('subject_agenda',args=[int(sub.id)]))
    try:
        lessons = SystemLesson.objects.filter(subject=sub_index, grade=grade, term=term.number)
    except Exception:
        lessons = None
    c = RequestContext(request,{'list': lessons, 'sub' : sub, 'grade' : grade})
    t = loader.get_template(os.path.join('school', 'use_system_agenda.html'))
    return HttpResponse(t.render(c))

@need_login
def use_system_agenda_for_school(request, subject, grade, term):
    school = get_school(request)
    pos = get_position(request)
    if pos < 4:
        return HttpResponseRedirect(reverse('index'))


    if request.method == 'POST':
        SchoolLesson.objects.filter(school = school, subject=subject, grade=grade, term=term).delete()
        lessSystem = SystemLesson.objects.filter(subject=subject, grade=grade, term=term)

        if lessSystem is not None:
            for iless in lessSystem:
                less = SchoolLesson()
                less.school = school
                less.index = iless.index
                less.subject = subject
                less.term = term
                less.note = iless.note
                less.title = iless.title
                less.save()

        return HttpResponseRedirect(reverse('school_subject_agenda',args=[subject, grade, term]))
    try:
        lessons = SystemLesson.objects.filter(subject=subject, grade=grade, term=term)
    except Exception:
        lessons = None
    c = RequestContext(request,{'list': lessons, 'sub' : subject, 'grade' : grade, 'term' : term, 'subject': SUBJECT_CHOICES[int(subject) - 1][1]})
    t = loader.get_template(os.path.join('school', 'use_system_agenda_for_school.html'))
    return HttpResponse(t.render(c))

def forget_password(request):
    if not request.user.is_anonymous():
        return HttpResponseRedirect(reverse('school_index'))
    form = ForgetPasswordForm()
    if request.method == 'POST':
        form = ForgetPasswordForm(request.POST)
        if form.is_valid():
            if not settings.IS_TESTING:
                captchar_check = captcha.submit(
                    request.POST['recaptcha_challenge_field'],
                    request.POST['recaptcha_response_field'],
                    settings.CAPTCHA_PRIVATE_KEY,
                    request.META['REMOTE_ADDR']
                )
                if not captchar_check.is_valid:
                    error = {'__all__':u'Hai từ bạn nhập không đúng'}
                    response = simplejson.dumps({
                        'success': False,
                        'err': error,
                        'message': u'Có lỗi ở dữ liệu nhập vào'})
                    return HttpResponse(response, mimetype='json')
            form.save()
            response = simplejson.dumps({
                'success':True,
                'message':u'Thông tin tài khoản đang được gửi vào email hoặc điện thoại của bạn.'
                          u' Xin vui lòng chờ trong ít phút'
            })
            return HttpResponse(response, mimetype='json')
        else:
            error = {}
            for k, v in form.errors.items():
                error[k] = form.error_class.as_text(v)
            response = simplejson.dumps({
                'success': False,
                'err': error,
                'message': u'Có lỗi ở dữ liệu nhập vào'})
            return HttpResponse(response, mimetype='json')
    return render_to_response(os.path.join('school','forget_password.html'),
        {'form':form},
        context_instance=RequestContext(request))
