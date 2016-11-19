from rest_framework_swagger.renderers import SwaggerUIRenderer
from django.shortcuts import render
from users.oauth_tools import get_access_token

class SwaggerCustomUIRenderer(SwaggerUIRenderer):
    template = 'swagger/index.html'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        self.set_context(renderer_context)
        token = get_access_token(renderer_context['request'].user)
        renderer_context['access_token'] = token
        return render(
            renderer_context['request'],
            self.template,
            renderer_context
        )
