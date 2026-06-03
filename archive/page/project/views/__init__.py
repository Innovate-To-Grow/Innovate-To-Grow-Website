from flask import Blueprint, render_template

from project import cache

home_blueprint = Blueprint("home", __name__, template_folder="../templates/home")


@home_blueprint.route("/2025-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2025():
    return render_template("2025-fall-event.html")


@home_blueprint.route("/2025-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2025():
    return render_template("2025-spring-event.html")


@home_blueprint.route("/2024-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2024():
    return render_template("2024-fall-event.html")


@home_blueprint.route("/2023-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2023():
    return render_template("2023-fall-event.html")


@home_blueprint.route("/2023-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2023():
    return render_template("2023-spring-event.html")


@home_blueprint.route("/2024-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2024():
    return render_template("2024-spring-event.html")


@home_blueprint.route("/2022-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2022():
    return render_template("2022-fall-event.html")


@home_blueprint.route("/2022-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2022():
    return render_template("2022-spring-event.html")


@home_blueprint.route("/2021-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2021():
    return render_template("2021-spring-event.html")


@home_blueprint.route("/2021-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2021():
    return render_template("2021-fall-event.html")


@home_blueprint.route("/2020-fall-post-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_post_2020():
    return render_template("2020-fall-post-event.html")
