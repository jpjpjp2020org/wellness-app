from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import authenticate

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        if email and password:
            user = authenticate(request=self.context.get('request'), email=email, password=password)
            if not user:
                raise AuthenticationFailed("Invalid credentials", code='authorization')
        else:
            raise AuthenticationFailed("Missing credentials", code='authorization')

        data = super().validate(attrs)
        data["user_id"] = user.user_id
        data["email"] = user.email
        return data
