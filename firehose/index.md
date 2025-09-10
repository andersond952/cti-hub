---
layout: default
title: Firehose
---

<link rel="stylesheet" href="{{ '/assets/css/custom.css' | relative_url }}"/>

# Firehose
Latest raw CTI snapshots.

<ul class="card-list">
{% assign files = site.pages | where_exp:"p","p.url contains '/firehose/'" | sort:"url" | reverse %}
{% for p in files %}
  {% if p.name != 'index.md' %}
    <li><a href="{{ p.url | relative_url }}">{{ p.url | split: '/' | last | replace:'.html','' }}</a></li>
  {% endif %}
{% endfor %}
</ul>
