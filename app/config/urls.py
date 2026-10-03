from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from library import accounts, views, annotation_views

urlpatterns = [
 path('',views.home,name='home'),path('healthz/',views.health),
 path('login/',accounts.AccountLoginView.as_view(),name='login'),
 path('account/login/',accounts.AccountLoginView.as_view(),name='account-login'),
 path('register/',accounts.register,name='register'),
 path('anonymous/',accounts.anonymous_login,name='anonymous-login'),
 path('logout/',auth.LogoutView.as_view(),name='logout'),
 path('password/',accounts.password,name='password'),
 path('admin/',admin.site.urls),path('upload/',views.upload,name='upload'),
 path('preview/<uuid:token>/',views.preview,name='preview'),
 path('preview/<uuid:token>/metadata/',views.stage_metadata,name='stage-metadata'),
 path('preview/<uuid:token>/files/<str:name>',views.stage_file,name='stage-file'),
 path('papers/<uuid:pk>/',views.reader,name='reader'),
 path('papers/<uuid:pk>/metadata/',views.paper_metadata,name='paper-metadata'),
 path('papers/<uuid:pk>/files/<str:name>',views.paper_file,name='paper-file'),
 path('papers/<uuid:pk>/revisions/<uuid:revision_id>/',annotation_views.revision_reader,name='revision-reader'),
 path('papers/<uuid:pk>/revisions/<uuid:revision_id>/files/<str:name>',annotation_views.revision_file,name='revision-file'),
 path('api/papers/<uuid:pk>/representation/',annotation_views.representation),
 path('api/papers/<uuid:pk>/annotations/',annotation_views.annotations),
 path('api/papers/<uuid:pk>/revisions/<uuid:revision_id>/pdf/',annotation_views.pdf_document,name='revision-pdf'),
 path('api/papers/<uuid:pk>/revisions/<uuid:revision_id>/pdf/pages/<int:page_index>/',annotation_views.pdf_page_text),
 path('api/papers/<uuid:pk>/ratings/',views.ratings),
 path('api/papers/<uuid:pk>/ratings/<str:dimension>/',views.rating),
 path('api/papers/<uuid:pk>/comments/',views.comments),
 path('api/papers/<uuid:pk>/comments/<int:comment_id>/',views.comment_detail),
 path('api/papers/<uuid:pk>/comments/<int:comment_id>/hide/',views.comment_hide),
]
