for /d %%i in (*) do java -jar selenium-server.jar -htmlSuite *iexplore "http://www.truongnha.com" %%i/suite.html results_%%i.html