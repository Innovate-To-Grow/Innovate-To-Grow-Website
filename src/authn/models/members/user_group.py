from django.contrib.auth.models import Group


class MemberGroup:
    # define all roles
    PROJECT_CLIENT = "I2G Project Client - Mentor"
    JUDGE = "Judge"
    VISITOR = "Visitor - Attendee"
    FAMILY_FRIENDS = "Family & Friends of I2G Student"
    STUDENT_NON_I2G = "Student (NON-I2G)"
    FACULTY_STAFF = "Faculty & Staff"

    GROUP_CHOICES = [
        PROJECT_CLIENT,
        JUDGE,
        VISITOR,
        FAMILY_FRIENDS,
        STUDENT_NON_I2G,
        FACULTY_STAFF,
    ]


class I2GMemberGroup(Group):
    # meta
    class Meta:
        proxy = True
        verbose_name = "I2G Member Group"
        verbose_name_plural = "I2G Member Groups"

    # create all groups automatically (idempotent, safe)
    @staticmethod
    def create_default_groups():
        for group_name in MemberGroup.GROUP_CHOICES:
            Group.objects.get_or_create(name=group_name)

    # get group display name
    @property
    def display_name(self):
        """
        Return a user-friendly display name for the group.
        """
        return self.name

    # check if group is a default I2G group
    def is_default_group(self):
        """
        Check if this group is one of the predefined I2G groups.
        """
        return self.name in MemberGroup.GROUP_CHOICES

    # get members count
    def get_members_count(self):
        """
        Return the number of users in this group.
        """
        return self.user_set.count()

    # add helper methods for group management
    def add_member(self, member):
        """
        Add a member to this group.
        """
        member.groups.add(self)

    def remove_member(self, member):
        """
        Remove a member from this group.
        """
        member.groups.remove(self)
