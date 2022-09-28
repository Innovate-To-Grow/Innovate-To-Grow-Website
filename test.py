from project.util.token import generate_token, confirm_token, confirm_token_no_expiry

token = generate_token("missingbeatrice")

print(confirm_token(token))
print(confirm_token_no_expiry(token))