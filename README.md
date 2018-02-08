# Asynchronous http server
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
wrk -c100 -d60s -t8 http://localhost:8080/
Running 1m test @ http://localhost:8080/
  8 threads and 100 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency    32.36ms   32.02ms   1.05s    99.48%
    Req/Sec   371.23    198.68     3.47k    89.51%
  172610 requests in 1.00m, 62.88MB read
  Socket errors: connect 0, read 0, write 0, timeout 37
  Non-2xx or 3xx responses: 172610
Requests/sec:   2872.92
Transfer/sec:      1.05MB
```
