from django.urls import path

from . import views

audio_patterns = [
    path("clips/", views.AudioClipUploadView.as_view(), name="audio-clips"),
    path("clips/<uuid:clip_id>/", views.AudioClipDetailView.as_view(), name="audio-clip"),
    path("clips/<uuid:clip_id>/content/", views.AudioClipContentView.as_view(), name="audio-clip-content"),
    path("transcribe/", views.TranscribeView.as_view(), name="audio-transcribe"),
    path("synthesise/", views.SynthesiseView.as_view(), name="audio-synthesise"),
    path("syntheses/<uuid:synthesis_id>/content/", views.SynthesisContentView.as_view(), name="audio-synthesis-content"),
]

interpretation_patterns = [
    path("", views.InterpretationCreateView.as_view(), name="interpretations"),
    path("<uuid:interpretation_id>/", views.InterpretationDetailView.as_view(), name="interpretation"),
    path("<uuid:interpretation_id>/confirm/", views.InterpretationConfirmView.as_view(), name="interpretation-confirm"),
]

instruction_patterns = [
    path("<slug:key>/audio/", views.InstructionAudioView.as_view(), name="instruction-audio"),
]
