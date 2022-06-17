def userRandomizer():
    # this function creates a random first and lastname as well as two email addresses
    # returns an array of [firstname, lastname, email1, email2]
    import random

    # size of firstnameArray = 25
    firstNameArray = ["Bob","Joe","Steve","Dillon","Marcus","Andy","Sally","Sue","Jane","Emily","Jessica","Anthony"]
    firstNameArray += ["Liam","Noah","James","Oliver","Ava","Isabella","Sophia","Mason","Evelyn","Mia","Amelia","Olivia","Ava"]

    # size of lastnameArray = 17
    lastNameArray = ["Phillips","Mendes","Wilson","Wheeler","Smith","Brown","Martinez","Anderson","Moore","Jackson","Harris","Perez","Clark","Taylor","Nguyen","Hill","Adams"]

    # firstname index
    fnIndex = random.randint(0,24)
    # lastname index
    lnIndex = random.randint(0,16)

    # use the random indexes to make filler names
    firstname = firstNameArray[fnIndex]
    lastname = lastNameArray[lnIndex]

    print(firstname)
    print(lastname)

    # making a random email address in the format firstInitial.lastname@gmail.com and firstname_lastname[0to99]@gmail.com
    email1 = firstname[0] + lastname + "@gmail.com"
    email1 = email1.lower() # lowercase all letters in email
    print(email1)

    randInt = random.randint(0,99)
    email2 = firstname + "_" + lastname + str(randInt) + "@gmail.com"
    email2 = email2.lower()
    print(email2)
    userArray = [firstname,lastname,email1,email2]
    return userArray