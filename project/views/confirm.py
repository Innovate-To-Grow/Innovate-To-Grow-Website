"""
OTP Confirmation View

Handles phone number verification via SMS OTP codes sent through Twilio.
This view processes the OTP verification after users complete registration
with phone numbers.
"""

from flask import Blueprint, request, render_template, session, flash, redirect, url_for
from datetime import datetime
from project.utils.utils import query_primary_column
import asyncio, time
from project import app, wks, tz, get_wks_records, get_wks_columns
from gspread.cell import Cell
from project.forms.otp_forms import OTPForm
from project.utils.twilio import client, verify_sid, check_verification, send_message


confirm_blueprint = Blueprint("confirm",
                             __name__,
                             template_folder="../templates/membership/events",
                             url_prefix=app.config["URL_PREFIX"])


@confirm_blueprint.route("/otp", methods=["GET", "POST"])
def otp():
    """
    Handle OTP verification for phone numbers.
    
    This route processes the OTP code entered by users and verifies it
    against Twilio's verification service. Upon successful verification,
    it updates the user's phone verification status and routes them to
    the appropriate success page.
    """
    form = OTPForm()

    if request.method == "POST" and form.validate_on_submit():
        # Retrieve session data set during registration
        event_url = session.get('event_url')
        update_url = session.get('update_url')
        first = session.get('first')
        last = session.get('last')
        primary_email = session.get('primary_email')
        primary_verified = session.get('primary_verified')
        primary_subscribed = session.get('primary_subscribed')
        secondary_email = session.get('secondary_email')
        secondary_verified = session.get('secondary_verified')  # Fixed typo
        secondary_subscribed = session.get('secondary_subscribed')  # Fixed typo
        phone_number = session.get('phone_number')
        info_fields = session.get('info_fields')
        event_fields = session.get('event_fields')
        event_reg = session.get('event_reg')
        phone_subscribe = session.get('phone_subscribe')
        event_name = session.get('event_name')
        update = session.get('update')
        origin = session.get('origin')

        # Default phone subscription to FALSE if not set
        if phone_subscribe != "TRUE":
            phone_subscribe = "FALSE"

        # Get OTP code from form
        otp = form.otp.data
        
        # Debug: Print session data
        print(f"DEBUG: Session data at start of OTP verification:")
        print(f"  - phone_subscribe: {phone_subscribe}")
        print(f"  - update: {update}")
        print(f"  - phone_number: {phone_number}")

        # Verify OTP with Twilio
        if check_verification(client, phone_number, verify_sid, otp) == "approved":
            # Retry logic to handle race condition (background thread might still be creating record)
            user = None
            for attempt in range(3):
                # Get worksheet records and columns
                wks_records = get_wks_records(wks)
                wks_columns = get_wks_columns(wks)

                # Find user by primary email
                user = asyncio.run(query_primary_column(primary_email, wks_records))
                
                if user:
                    # Record found, proceed with verification
                    user = user[0]
                    break
                elif attempt < 2:
                    # Wait and retry
                    print(f"DEBUG: User record not found yet, retrying (attempt {attempt + 1}/3)")
                    time.sleep(1)
                else:
                    # Final attempt failed
                    flash("Registration still processing. Please try again in a moment.", "warning")
                    return render_template("otp.html", form=form)
            
            # User found, update phone verification
            if user:
                row_find = user["Row"]

                # Update the phone verification status and subscription
                cells = []
                cells.append(Cell(row_find, wks_columns["Phone number verified"], "TRUE"))
                cells.append(Cell(row_find, wks_columns["Phone number subscribed"], phone_subscribe))
                cells.append(Cell(row_find, wks_columns["Last Updated"],
                                str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))))

                # Debug: Print what we're updating
                print(f"DEBUG: Updating phone verification status:")
                print(f"  - Phone number verified: TRUE")
                print(f"  - Phone number subscribed: {phone_subscribe}")
                print(f"  - Row: {row_find}")
                print(f"  - Column for Phone number subscribed: {wks_columns['Phone number subscribed']}")

                # Update the worksheet
                wks.update_cells(cells)
                
                # Debug: Verify the update was successful
                print(f"DEBUG: After update, checking cell value:")
                updated_cell = wks.cell(row_find, wks_columns["Phone number subscribed"])
                print(f"  - Cell value: '{updated_cell.value}'")
                
                # Add a small delay to ensure database update is committed
                time.sleep(1)

            # Send confirmation SMS if appropriate
            if event_reg == "yes" and phone_subscribe == "TRUE" and event_name is not None:
                send_message(f"You have signed up for {event_name}", phone_number, client)
            elif update == "TRUE" and phone_subscribe == "TRUE" and event_name is not None:
                # Update flow with event registration - send confirmation
                send_message(f"You have signed up for {event_name}", phone_number, client)

            print(f"Update flag: {update}")
            print(f"Event registration: {event_reg}")

            # Route to appropriate success page based on context
            if update == "TRUE":
                # This was an update flow, redirect to update success page
                # Since OTP was successfully verified, phone is now verified
                phone_number_verified = "TRUE"
                # phone_subscribe is already set from session data above (as "TRUE" or "FALSE" string)
                
                return render_template("thanks_update.html",
                                       event_url=event_url,
                                       update_url=update_url,
                                       first=first,
                                       last=last,
                                       primary_email=primary_email,
                                       primary_verified=primary_verified,
                                       primary_subscribed=primary_subscribed,
                                       secondary_email=secondary_email,
                                       secondary_verified=secondary_verified,
                                       secondary_subscribed=secondary_subscribed,
                                       phone_number=phone_number,
                                       phone_number_verified=phone_number_verified,
                                       phone_subscribed=phone_subscribe,
                                       info_fields=info_fields,
                                       event_name=event_name,
                                       event_fields=event_fields)
            else:
                # This was a new registration flow
                if event_reg == "yes":
                    # User registered for an event, show event success page
                    # Since OTP was successfully verified, phone is now verified
                    phone_number_verified = "TRUE"
                    # phone_subscribe is already set from session data above (as "TRUE" or "FALSE" string)
                    
                    return render_template("successfully_registered.html",
                                           event_url=event_url,
                                           update_url=update_url,
                                           first=first,
                                           last=last,
                                           primary_email=primary_email,
                                           primary_verified=primary_verified,
                                           primary_subscribed=primary_subscribed,
                                           secondary_email=secondary_email,
                                           secondary_verified=secondary_verified,
                                           secondary_subscribed=secondary_subscribed,
                                           phone_number=phone_number,
                                           phone_number_verified=phone_number_verified,
                                           phone_subscribed=phone_subscribe,
                                           info_fields=info_fields,
                                           event_name=event_name,
                                           event_fields=event_fields)
                else:
                    # Branch based on origin: new signup should return instructions_sent
                    if origin == "signup":
                        return render_template("instructions_sent.html")
                    # Regular registration completion, show receipt page
                    # Since OTP was successfully verified, phone is now verified
                    phone_number_verified = "TRUE"
                    # phone_subscribe is already set from session data above
                    
                    return render_template("receipt.html",
                                           event_url=event_url,
                                           update_url=update_url,
                                           first=first,
                                           last=last,
                                           primary_email=primary_email,
                                           primary_verified=primary_verified,
                                           primary_subscribed=primary_subscribed,
                                           secondary_email=secondary_email,
                                           secondary_verified=secondary_verified,
                                           secondary_subscribed=secondary_subscribed,
                                           phone_number=phone_number,
                                           phone_number_verified=phone_number_verified,
                                           phone_subscribe=phone_subscribe,
                                           info_fields=info_fields,
                                           event_name=event_name,
                                           event_fields=event_fields)
        else:
            # OTP verification failed
            flash("Invalid verification code. Please try again.", "error")
            return render_template("otp.html", form=form)

    else:
        # GET request - show OTP form
        return render_template("otp.html", form=form)