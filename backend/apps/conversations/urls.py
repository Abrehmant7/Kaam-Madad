from django.urls import path

from . import views

urlpatterns = [
    path("<uuid:invitation_id>/", views.ConversationView.as_view(), name="conversation"),
    path("<uuid:invitation_id>/messages/", views.MessagesView.as_view(), name="conversation-messages"),
    path("<uuid:invitation_id>/messages/<uuid:message_id>/audio/", views.MessageAudioView.as_view(), name="conversation-message-audio"),
    path("<uuid:invitation_id>/quotes/", views.QuotesView.as_view(), name="conversation-quotes"),
    path("<uuid:invitation_id>/quotes/draft/", views.QuoteDraftView.as_view(), name="conversation-quote-draft"),
    path("<uuid:invitation_id>/quotes/draft/submit/", views.QuoteSubmitView.as_view(), name="conversation-quote-submit"),
    path("<uuid:invitation_id>/quotes/<uuid:quote_id>/", views.QuoteDetailView.as_view(), name="conversation-quote"),
    path("<uuid:invitation_id>/quotes/<uuid:quote_id>/check/", views.QuoteCheckView.as_view(), name="conversation-quote-check"),
    path("<uuid:invitation_id>/quotes/<uuid:quote_id>/manual-review/", views.ManualReviewView.as_view(), name="conversation-quote-manual-review"),
    path("<uuid:invitation_id>/quotes/<uuid:quote_id>/findings/<uuid:finding_id>/resolve/", views.FindingResolveView.as_view(),
         name="conversation-finding-resolve"),
    path("<uuid:invitation_id>/readiness/", views.ReadinessView.as_view(), name="conversation-readiness"),
]
