运行 `python -m app.demo` 会报错；另外有用户反映，即使没有开启 debug，服务也打印了 "debug mode on"。

请找出原因并修复：让配置项返回正确的类型（page_size 和 timeout 为 int；debug 为 bool，"true"、"1"、"yes" 不区分大小写都算开启，其他值算关闭），同时环境变量（如 APP_PAGE_SIZE、APP_DEBUG）仍然可以覆盖默认值。
