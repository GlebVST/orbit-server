from rest_framework_swagger.renderers import SwaggerUIRenderer
from django.shortcuts import render
from users.oauth_tools import get_access_token, new_access_token

class SwaggerCustomUIRenderer(SwaggerUIRenderer):
    template = 'swagger/index.html'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        self.set_context(renderer_context)
        user = renderer_context['request'].user
        token = None
        if user.is_authenticated():
            token = get_access_token(user)
            if not token:
                token = new_access_token(user)
        # Set access_token in renderer_context to enable Authorization: Bearer <token> in request header
        renderer_context['access_token'] = token
        return render(
            renderer_context['request'],
            self.template,
            renderer_context
        )
