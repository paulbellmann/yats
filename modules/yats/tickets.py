# -*- coding: utf-8 -*- 
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.http.response import HttpResponseRedirect, StreamingHttpResponse
from django.db.models import get_model
from django.conf import settings
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.utils.encoding import smart_str
from yats.forms import TicketsForm, CommentForm, UploadFileForm
from yats.models import tickets_files, tickets_comments
from yats.shortcuts import resize_image
import os
import io

def new(request):
    excludes = ['resolution']
    
    if request.method == 'POST':
        form = TicketsForm(request.POST, exclude_list=excludes, is_stuff=request.user.is_staff, user=request.user)
        if form.is_valid():
            tic = form.save()
            
            if form.cleaned_data.get('file_addition', False):
                return HttpResponseRedirect('/tickets/upload/%s/' % tic.pk)
            else:
                return HttpResponseRedirect('/tickets/view/%s/' % tic.pk)
    
    else:
        form = TicketsForm(exclude_list=excludes, is_stuff=request.user.is_staff, user=request.user)
    
    return render_to_response('tickets/new.html', {'layout': 'horizontal', 'form': form}, RequestContext(request))    

def action(request, mode, ticket):
    mod_path, cls_name = settings.TICKET_CLASS.rsplit('.', 1)
    mod_path = mod_path.split('.').pop(0)
    tic = get_model(mod_path, cls_name).objects.get(pk=ticket)

    if mode == 'view':
        if request.method == 'POST':
            form = CommentForm(request.POST)
            if form.is_valid():
                com = tickets_comments()
                com.comment = form.cleaned_data['comment']
                com.ticket_id = ticket
                com.save(user=request.user)
                
            else:
                messages.add_message(request, messages.ERROR, _('comment invalid'))
        
        excludes = []        
        form = TicketsForm(exclude_list=excludes, is_stuff=request.user.is_staff, user=request.user, instance=tic)
        
        files = tickets_files.objects.filter(ticket=ticket)
        paginator = Paginator(files, 10)
        page = request.GET.get('page')
        try:
            files_lines = paginator.page(page)
        except PageNotAnInteger:
            # If page is not an integer, deliver first page.
            files_lines = paginator.page(1)
        except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of results.
            files_lines = paginator.page(paginator.num_pages)
        
        comments = tickets_comments.objects.select_related('c_user').filter(ticket=ticket)
        paginator = Paginator(comments, 10)
        page = request.GET.get('page')
        try:
            comments_lines = paginator.page(page)
        except PageNotAnInteger:
            # If page is not an integer, deliver first page.
            comments_lines = paginator.page(1)
        except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of results.
            comments_lines = paginator.page(paginator.num_pages)

        return render_to_response('tickets/view.html', {'layout': 'horizontal', 'ticket': tic, 'form': form, 'files': files_lines, 'comments': comments_lines}, RequestContext(request))

    elif mode == 'edit':
        excludes = ['resolution']
        if request.method == 'POST':
            form = TicketsForm(request.POST, exclude_list=excludes, is_stuff=request.user.is_staff, user=request.user, instance=tic)
            if form.is_valid():
                tic = form.save()
                return HttpResponseRedirect('/tickets/view/%s/' % tic.pk)
        
        else:
            form = TicketsForm(exclude_list=excludes, is_stuff=request.user.is_staff, user=request.user, instance=tic)
        
        return render_to_response('tickets/edit.html', {'ticketid': ticket, 'layout': 'horizontal', 'form': form}, RequestContext(request))    

    elif mode == 'download':
        fileid = request.GET.get('file', -1)
        file_data = tickets_files.objects.get(id=fileid, ticket=ticket)
        src = '%s%s.dat' % (settings.FILE_UPLOAD_PATH, fileid)
        
        if request.GET.get('resize', 'no') == 'yes' and 'image' in file_data.content_type:
            img = resize_image('%s' % (src), (200, 150), 75)
            output = io.BytesIO()
            img.save(output, 'PNG')
            output.seek(0)
            response = StreamingHttpResponse(output, mimetype=smart_str(file_data.content_type))
            
        else:
            response = StreamingHttpResponse(open('%s' % (src),"rb"), mimetype=smart_str(file_data.content_type))
        response['Content-Disposition'] = 'attachment;filename=%s' % smart_str(file_data.name)
        return response
    
    elif mode == 'upload':
        if request.method == 'POST':
            form = UploadFileForm(request.POST, request.FILES)
            if form.is_valid():
                f = tickets_files()
                f.name = request.FILES['file'].name
                f.size = request.FILES['file'].size
                f.content_type = request.FILES['file'].content_type
                f.ticket_id = ticket
                f.public = True
                f.save(user=request.user)
                
                dest = settings.FILE_UPLOAD_PATH
                if not os.path.exists(dest):
                    os.makedirs(dest)
    
                with open('%s%s.dat' % (dest, f.id), 'wb+') as destination:
                    for chunk in request.FILES['file'].chunks():
                        destination.write(chunk)
                        
                return HttpResponseRedirect('/tickets/view/%s/' % tic.pk) 
        else:
            form = UploadFileForm()
        
        return render_to_response('tickets/file.html', {'ticketid': ticket, 'layout': 'horizontal', 'form': form}, RequestContext(request))    

def table(request):
    mod_path, cls_name = settings.TICKET_CLASS.rsplit('.', 1)
    mod_path = mod_path.split('.').pop(0)
    tic = get_model(mod_path, cls_name).objects.all()

    if not request.user.is_staff:
        tic = tic.filter(customer=request.organisation)

    paginator = Paginator(tic, 10)
    page = request.GET.get('page')
    try:
        tic_lines = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        tic_lines = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        tic_lines = paginator.page(paginator.num_pages)

    return render_to_response('tickets/list.html', {'lines': tic_lines}, RequestContext(request))