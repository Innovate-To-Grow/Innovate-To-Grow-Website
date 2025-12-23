from ..models import *
from typing import (
    List,
    Optional,
    Any,
    Dict,
)
from django.db import transaction

class CreateMemberService:

    @staticmethod
    # database transaction decorator (disable for development)
    @transaction.atomic
    def create_member(
            # field for user
            username: str,
            password: str,

            first_name: str,
            last_name: str,
            # field for


    ) -> Dict[str, Any]:
        """
        create a new member

        :arg
            username: str

        :return:
        """



        pass