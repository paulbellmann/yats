from django.db.models import get_model
from django.conf import settings
from django.core.mail import send_mail
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _
from django.forms.forms import pretty_name
from yats.models import tickets_participants, tickets_comments, tickets_files, tickets_history, ticket_flow

from PIL import Image#, ImageOps
import sys
import datetime
import re

try:
    import json
except ImportError:
    from django.utils import simplejson as json
    
def resize_image(filename, size=(200, 150), dpi=75):
    image = Image.open(filename)
    pw = image.size[0]
    ph = image.size[1]
    nw = size[0]
    nh = size[1]

    # icon generell too small or equal
    if (pw < nw and ph < nh) or (pw == nw and ph == nh):
        if image.format.lower() == 'jpg' or image.format.lower() == 'jpeg':
            return image
                     
    else:
        pr = float(pw) / float(ph)
        nr = float(nw) / float(nh)
        
        if pr > nr:
            # icon aspect is wider than destination ratio
            tw = int(round(nh * pr))
            image = image.resize((tw, nh), Image.ANTIALIAS)
            l = int(round(( tw - nw ) / 2.0))
            image = image.crop((l, 0, l + nw, nh))
        elif pr < nr:
            # icon aspect is taller than destination ratio
            th = int(round(nw / pr))
            image = image.resize((nw, th), Image.ANTIALIAS)
            t = int(round(( th - nh ) / 2.0))
            image = image.crop((0, t, nw, t + nh))
        else:
            # icon aspect matches the destination ratio
            image = image.resize(size, Image.ANTIALIAS)
            
    if image.mode != "RGB":
        # http://packages.debian.org/search?keywords=python-imaging
        # if thumb_image.mode == "CMYK":
        #    thumb_image = ImageOps.invert(thumb_image)
        image = image.convert('RGB')
    return image

def get_ticket_model():
    mod_path, cls_name = settings.TICKET_CLASS.rsplit('.', 1)
    mod_path = mod_path.split('.').pop(0)
    return get_model(mod_path, cls_name)

def touch_ticket(user, ticket_id):
    tickets_participants.objects.get_or_create(ticket_id=ticket_id, user=user)
    
def get_recipient_list(request, ticket_id):
    pub_result = []
    int_result = []
    error = []
    rcpts = tickets_participants.objects.select_related('user').filter(ticket=ticket_id)
    for rcpt in rcpts:
        # leave out myself
        if rcpt.user != request.user:
            if rcpt.user.email:
                if rcpt.user.is_staff:
                    int_result.append(rcpt.user.email)
                else:
                    pub_result.append(rcpt.user.email)
            else:
                error.append(unicode(rcpt.user))
    if len(error) > 0:
        messages.add_message(request, messages.ERROR, _('the following participants could not be reached by mail (address missing): %s') % ', '.join(error))
    return int_result, pub_result
    
def get_ticket_url(request, ticket_id):
    if request.is_secure():
        return 'https://%s/tickets/view/%s/' % (request.get_host(), ticket_id)
    else:
        return 'http://%s/tickets/view/%s/' % (request.get_host(), ticket_id)

def modulePathToModuleName(mod_path):
    path = mod_path.split('.')
    if len(path) > 1:
        path.pop()
    return path.pop()
    
def getModelValue(mod_path, cls_name, value):
    mod_path = modulePathToModuleName(mod_path)
    try:
        return unicode(get_model(mod_path, cls_name).objects.get(pk=value))
    except:
        return u''

def getNameOfModelValue(field, value):
    cls_name = field.__class__.__name__
    mod_path = field.__class__.__module__
    return getModelValue(mod_path, cls_name, value)

def field_changes(form):
    new = {}
    old = {}
    cd = form.cleaned_data
    
    for field in form.changed_data:
        if type(cd.get(field)) not in [bool, int, str, unicode, long, None, datetime.date]:
            if cd.get(field):
                new[field] = unicode(cd.get(field))
                old[field] = getNameOfModelValue(cd.get(field), form.initial.get(field))
            else:
                new[field] = unicode(cd.get(field))
                if type(form.initial.get(field)) != None:
                    old[field] = unicode(form.initial.get(field))
                else:
                    old[field] = unicode(None)
        else:
            new[field] = unicode(cd.get(field))
            old[field] = unicode(form.initial.get(field))
            
    return new, old

def has_public_fields(data):
    for field in data:
        if field not in settings.TICKET_NON_PUBLIC_FIELDS:
            return True
    return False

def format_chanes(new, is_staff):
    result = []
    for field in new:
        if not is_staff and field in settings.TICKET_NON_PUBLIC_FIELDS:
            continue
        result.append('%s: %s' % (pretty_name(field), new[field]))
        
    return '\n'.join(result)

def mail_ticket(request, ticket_id, form, **kwargs):
    int_rcpt, pub_rcpt = list(get_recipient_list(request, ticket_id))
    if 'rcpt' in kwargs and kwargs['rcpt']:
        int_rcpt.append(kwargs['rcpt'])
    tic = get_ticket_model().objects.get(pk=ticket_id)

    new, old = field_changes(form)

    if len(int_rcpt) > 0:
        try:
            new['author'] = tic.c_user
            send_mail('%s#%s - %s' % (settings.EMAIL_SUBJECT_PREFIX, tic.id, tic.caption), '%s\n\n%s' % (format_chanes(new, True), get_ticket_url(request, ticket_id)), settings.SERVER_EMAIL, int_rcpt, False)
        except:
            if not kwargs.get('is_api', False):
                messages.add_message(request, messages.ERROR, _('mail not send: %s') % sys.exc_info()[1])
            
    if len(pub_rcpt) > 0 and has_public_fields(new):
        try:
            new['author'] = tic.u_user
            send_mail('%s#%s - %s' % (settings.EMAIL_SUBJECT_PREFIX, tic.id, tic.caption), '%s\n\n%s' % (format_chanes(new, False), get_ticket_url(request, ticket_id)), settings.SERVER_EMAIL, pub_rcpt, False)
        except:
            if not kwargs.get('is_api', False):
                messages.add_message(request, messages.ERROR, _('mail not send: %s') % sys.exc_info()[1])
        
def mail_comment(request, comment_id):
    com = tickets_comments.objects.get(pk=comment_id)
    ticket_id = com.ticket_id
    int_rcpt, pub_rcpt = get_recipient_list(request, ticket_id)
    rcpt = int_rcpt + pub_rcpt
    if len(rcpt) == 0:
        return
    
    tic = get_ticket_model().objects.get(pk=ticket_id)
    
    try:    
        send_mail('%s#%s: %s - %s' % (settings.EMAIL_SUBJECT_PREFIX, tic.id, _('new comment'), tic.caption), '%s\n\n%s' % (com.comment, get_ticket_url(request, ticket_id)), settings.SERVER_EMAIL, rcpt, False)
    except:
        messages.add_message(request, messages.ERROR, _('mail not send: %s') % sys.exc_info()[1])        

def mail_file(request, file_id):
    io = tickets_files.objects.get(pk=file_id)
    ticket_id = io.ticket_id
    int_rcpt, pub_rcpt = get_recipient_list(request, ticket_id)
    rcpt = int_rcpt + pub_rcpt
    if len(rcpt) == 0:
        return
    tic = get_ticket_model().objects.get(pk=ticket_id)
    body = '%s\n%s: %s\n%s: %s\n%s: %s\n\n%s' % (_('new file added'), _('file name'), io.name, _('file size'), io.size, _('content type'), io.content_type, get_ticket_url(request, ticket_id))

    try:    
        send_mail('%s#%s: %s - %s' % (settings.EMAIL_SUBJECT_PREFIX, tic.id, _('new file'), tic.caption), body, settings.SERVER_EMAIL, rcpt, False)
    except:
        messages.add_message(request, messages.ERROR, _('mail not send: %s') % sys.exc_info()[1])
        
def clean_search_values(search):
    result = {}
    for ele in search:
        if type(search[ele]) not in [bool, int, str, unicode, long, None, datetime.date]:
            if search[ele]:
                result[ele] = search[ele].pk
        else:
            result[ele] = search[ele]
    return result         

def check_references(request, src_com):
    refs = re.findall('#([0-9]+)', src_com.comment) 
    for ref in refs:
        com = tickets_comments()
        com.comment = _('ticket mentioned by #%s' % src_com.ticket_id)
        com.ticket_id = ref
        com.action = 3
        com.save(user=request.user)
        
        touch_ticket(request.user, ref)
        
        #mail_comment(request, com.pk)

def remember_changes(request, form, ticket):
    new, old = field_changes(form)
            
    h = tickets_history()
    h.ticket = ticket
    h.new = json.dumps(new)
    h.old = json.dumps(old)
    h.action = 4
    h.save(user=request.user)
    
def add_history(request, ticket, typ, data):
    if typ == 5: 
        old = {'file': ''}
        new = {'file': data}
    elif typ == 6:
        old = {'comment': ''}
        new = {'comment': data}
    elif typ == 7:
        old = {
               'comment': '',
               'assigned': data['old']['assigned'],
               'state': data['old']['state']
               }
        new = {
               'comment': data['new']['comment'],
               'assigned': data['new']['assigned'],
               'state': data['new']['state']
               }
    elif typ == 3:
        old = {'reference': ''}
        new = {'reference': '#%s' % data}
    elif typ == 2:
        old = {'closed': unicode(True)}
        new = {'closed': unicode(False)}
        if data:
            old['comment'] = ''
            new['comment'] = data
    elif typ == 1:
        old = {'closed': unicode(False)}
        new = {'closed': unicode(True)}
        
    h = tickets_history()
    h.ticket = ticket
    h.new = json.dumps(new)
    h.old = json.dumps(old)
    h.action = typ
    h.save(user=request.user)
    
def getTicketField(field):
    tickets = get_ticket_model()
    m = tickets()
    try:
        return m._meta.get_field(field)
    except:
        return None
    
def prettyValues(data):
    result = {}
    for ele in data:
        ticket_field = getTicketField(ele)
        if type(ticket_field).__name__ == 'ForeignKey':
            if ele == 'c_user':
                result['creator'] = User.objects.get(pk=data[ele])
            elif ele == 'assigned':
                result['assigned'] = User.objects.get(pk=data[ele])
            else:
                result[ele] = getModelValue(ticket_field.rel.to.__module__, ticket_field.rel.to.__name__, data[ele])
        else:
            result[ele] = data[ele]
    return result

def add_breadcrumbs(request, pk, typ):
    breadcrumbs = request.session.get('breadcrumbs', [])
    # checks if already exists
    if len(breadcrumbs) > 0:
        if breadcrumbs[-1][0] != long(pk) or breadcrumbs[-1][1] != typ:
            if (long(pk), typ,) in breadcrumbs:
                breadcrumbs.pop(breadcrumbs.index((long(pk), typ,)))
            breadcrumbs.append((long(pk), typ,))
            
    else:
        breadcrumbs.append((long(pk), typ,))
    while len(breadcrumbs) > 10:
        breadcrumbs.pop(0)
    request.session['breadcrumbs'] = breadcrumbs
