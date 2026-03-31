
import dash
import dash_bootstrap_components as dbc
from dash import html


app = dash.Dash(external_stylesheets=[dbc.themes.MINTY])
app.title = "Dash demo"
server = app.server

app.layout = dbc.Container(
    [
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H2("My Dash Page"),
                        html.H5("Checking connection"),
                    ],
                    width=True,
                ),
            ],
            align="end",
        ),

    ],
    fluid=True,
)



try:  # wrapping this, since a forum post said it may be deprecated at some point.
    app.title = "Aircraft Design with Dash"
except:
    print("Could not set the page title!")


if __name__ == "__main__":
    app.run(debug=True)