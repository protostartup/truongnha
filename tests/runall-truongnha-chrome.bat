for /d %%i in (*) do java -jar selenium-server.jar -htmlSuite *googlechrome "http://www.truongnha.com" %%i/suite.html %%i/results.html