---
layout: default
title: Curated
---

<link rel="stylesheet" href="{{ '/assets/css/cards.css' | relative_url }}"/>

# Curated

Browse curated pages (vendor watches, monthly highlights).

## Vendor Watch
<ul class="card-list">
{% assign pages = site.pages | where_exp:"p","p.url contains '/curated/vendors/'" | sort:"url" %}
{% for p in pages %}
  {% if p.name != 'index.md' %}
    <li class="card"><div>
      <h3><a href="{{ p.url | relative_url }}">{{ p.url | split:'/' | last | replace:'.html','' }}</a></h3>
      <div class="meta">Vendor-focused feed lens</div>
    </div></li>
  {% endif %}
{% endfor %}
</ul>

## Monthly/Quarterly Highlights
<ul class="card-list">
{% assign months = site.pages | where_exp:"p","p.url contains '/curated/' and p.url not contains '/curated/vendors/'" | sort:"url" | reverse %}
{% for p in months %}
  {% if p.name != 'index.md' %}
    <li class="card"><div>
      <h3><a href="{{ p.url | relative_url }}">{{ p.url | split:'/' | last | replace:'.html','' }}</a></h3>
      <div class="meta">Analyst summaries</div>
    </div></li>
  {% endif %}
{% endfor %}
</ul>
