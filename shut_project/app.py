try:
    from shut_project.shut_app import create_app
except ModuleNotFoundError:
    from shut_app import create_app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8082, debug=False)
