for /d %%i in (*) do java -jar selenium-server.jar -htmlSuite *firefox "http://localhost:8000/" %%i/suite.html %%i/results.html