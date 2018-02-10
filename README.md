# Asynchronous http server
### Требования:
- python 2.7
## Веб‑сервер умеет:
- Масштабироваться на несколько worker'ов
- Числов worker'ов задается аргументом командной строки ‑w
- Отвечать 200 или 404 на GET‑запросы и HEAD‑запросы
- Отвечать 405 на прочие запросы
- Возвращать файлы по произвольному пути в DOCUMENT_ROOT.
- Вызов /file.html должен возвращать содердимое DOCUMENT_ROOT/file.html
- DOCUMENT_ROOT задается аргументом командной строки ‑r
- Возвращать index.html как индекс директории
- Вызов /directory/ должен возвращать DOCUMENT_ROOT/directory/index.html
- Отвечать следующими заголовками для успешных GET‑запросов: Date, Server, Content‑Length, Content‑Type, Connection
- Корректный Content‑Type для: .html, .css, .js, .jpg, .jpeg, .png, .gif, .swf
- Понимать пробелы и %XX в именах файлов

### Результаты нагрузочного тестирования:
```
wrk -c100 -d30s -t5 http://localhost:8080/
Running 30s test @ http://localhost:8080/
  5 threads and 100 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency    26.23ms   71.11ms   1.89s    99.36%
    Req/Sec   730.74    329.27     2.58k    74.80%
  109254 requests in 30.05s, 39.80MB read
  Socket errors: connect 0, read 0, write 0, timeout 18
  Non-2xx or 3xx responses: 109254
Requests/sec:   3635.75
Transfer/sec:      1.32MB

wrk -c100 -d60s -t8 http://localhost:8080/
Running 1m test @ http://localhost:8080/
  8 threads and 100 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency    34.32ms   45.23ms   1.92s    99.10%
    Req/Sec   371.35    160.80     1.77k    79.28%
  177337 requests in 1.00m, 64.60MB read
  Non-2xx or 3xx responses: 177337
Requests/sec:   2950.79
Transfer/sec:      1.07MB
```
