---
layout: default
title: Firehose
---

# Firehose

Latest raw CTI snapshots.

<ul>
{% assign fh = site.static_files | where_exp: "f", "f.path contains '/firehose/'" %}
{% assign fh = fh | sort: "modified_time" | reverse %}
{% for f in fh %}
  {% if f.extname == '.md' and f.name != 'index.md' %}
    <li><a href="{{ f.path | relative_url }}">{{ f.name | replace:'.md','' }}</a></li>
  {% endif %}
{% endfor %}
</ul>
