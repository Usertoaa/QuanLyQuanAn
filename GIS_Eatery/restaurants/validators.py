from django.contrib.auth.password_validation import (
    CommonPasswordValidator,
    MinimumLengthValidator,
    NumericPasswordValidator,
    UserAttributeSimilarityValidator,
)


class VietnameseUserAttributeSimilarityValidator(UserAttributeSimilarityValidator):
    def get_error_message(self):
        return "Mật khẩu quá giống với %(verbose_name)s của bạn."

    def get_help_text(self):
        return "Mật khẩu không được quá giống với thông tin cá nhân của bạn."


class VietnameseMinimumLengthValidator(MinimumLengthValidator):
    def get_error_message(self):
        return "Mật khẩu phải có ít nhất %(min_length)d ký tự."

    def get_help_text(self):
        return "Mật khẩu phải có ít nhất %(min_length)d ký tự." % {
            "min_length": self.min_length,
        }


class VietnameseCommonPasswordValidator(CommonPasswordValidator):
    def get_error_message(self):
        return "Mật khẩu này quá phổ biến."

    def get_help_text(self):
        return "Mật khẩu không được là mật khẩu quá phổ biến."


class VietnameseNumericPasswordValidator(NumericPasswordValidator):
    def get_error_message(self):
        return "Mật khẩu không được chỉ chứa chữ số."

    def get_help_text(self):
        return "Mật khẩu không được chỉ chứa chữ số."
