type RequiredNameFields = {
  first_name?: string | null;
  last_name?: string | null;
};

export const hasRequiredNameFields = (value: RequiredNameFields | null | undefined): boolean => {
  if (!value) {
    return false;
  }
  return Boolean(value.first_name?.trim() && value.last_name?.trim());
};
