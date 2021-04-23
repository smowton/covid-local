#!/usr/bin/python

import subprocess
import csv
import datetime
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.dates
import matplotlib.pyplot as plt
import os.path
import sys
import time
import urllib

if len(sys.argv) != 2:
  print >>sys.stderr, "Usage: covid-local.py outdir"
  sys.exit(1)

outdir = sys.argv[1]

def try_fetch(url):
  print url
  curl_proc = subprocess.Popen(["curl", "-s", "-S", "-L", "-m", "30", url], stdout=subprocess.PIPE)
  ret = subprocess.check_output(["gzip", "-d"], stdin = curl_proc.stdout)
  assert curl_proc.wait() == 0
  return ret

def robust_fetch(url):
  lastfail = None
  for attempts in range(6):
    try:
      return try_fetch(url)
    except Exception as e:
      if attempts == 5:
        print "Fetch", url, "keeps failing; backing off for 10 minutes..."
        time.sleep(60 * 10)
      else:
        print "Fetch", url, "failed; pausing 10 seconds..."
        time.sleep(10)
      lastfail = e
  raise lastfail

def escape(url):
  return url.replace(" ", "%20").replace("{", "%7B").replace("}", "%7D")

def fetch_all(url):
  data = []
  while url is not None:
    result = json.loads(robust_fetch(url))
    data.extend(result["data"])
    if "pagination" in result and "next" in result["pagination"] and result["pagination"]["next"] is not None:
      url = 'https://api.coronavirus.data.gov.uk' + escape(result["pagination"]["next"])
    else:
      url = None
  return data

regions = {}

for region_type in ["nation", "region", "utla", "ltla"]:
  print "Fetching data for region type '%s'" % region_type
  alldata = fetch_all('https://api.coronavirus.data.gov.uk/v1/data?format=json&filters=areaType={0}&structure=%7B%22name%22%3A%22areaName%22%2C%20%22cases%22%3A%22newCasesBySpecimenDate%22%2C%20%22date%22%3A%20%22date%22%7D'.format(region_type))

  for rec in alldata:
    region_name, date_str, cases = rec["name"], rec["date"], rec["cases"]
    date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    cases = int(cases)
    key = (region_name, region_type)
    if key not in regions:
      regions[key] = []
    regions[key].append((date_str, date, cases))

def seven_day_avg(idx, recs):
  avg_of = recs[max(idx - 3, 0) : idx + 4]
  return sum(rec[2] for rec in avg_of) / float(len(avg_of))

def escape(fname):
  return "".join(c if c.isalpha() else "_" for c in fname)

def pad_series(recs):
  out = []
  day = datetime.timedelta(1)
  for rec in recs:
    if len(out) != 0:
      day_before = rec[1] - day
      while out[-1][1] != day_before:
        next_day = out[-1][1] + day
        out.append((datetime.datetime.strftime(next_day, "%Y-%m-%d"), next_day, 0))
    out.append(rec)
  return out

def clean_and_add_averages(records):
  records = sorted(records, key = lambda rec: rec[1])
  records = pad_series(records)
  records = [(date_str, date, cases, seven_day_avg(i, records)) for (i, (date_str, date, cases)) in enumerate(records)]
  return records

def write_graph(region_name, region_type, records):
  print "Graph", region_name, region_type
  first_date = min(rec[1] for rec in records)
  fname = os.path.join(outdir, escape(region_name + " " + region_type))
  fig, ax = plt.subplots(figsize=(12, 8), dpi=100)
  xvals = [matplotlib.dates.date2num(rec[1]) for rec in records]
  avgvals = [rec[3] for rec in records][:-5] # Omit the last 5 days' averages, which are unreliable due to processing times
  dayvals = [rec[2] for rec in records]
  ax.plot_date(xvals[:-5], avgvals, "b-")
  ax.bar(xvals, dayvals, color = (0.8, 0.8, 0.8, 1.0))
  ax.set(xlabel = "Date", ylabel = "Cases per day", title = region_name)
  fig.savefig(fname)
  plt.close()

end_of_spring = datetime.datetime(2020, 7, 1)

def region_stats(region_name, region_type):
  recs = regions[(region_name, region_type)]
  recent_cases = sum(rec[2] for rec in recs[-14:])
  peak_rec = max(recs, key = lambda rec: rec[3])
  try:
    spring_peak_rec = max((r for r in recs if r[1] <= end_of_spring), key = lambda rec: rec[3])
  except ValueError:
    # Fallback for places with no Spring cases
    spring_peak_rec = peak_rec
  return {
    "peak": peak_rec[1],
    "recent_cases": recent_cases,
    "recent_rel_spring_peak": recent_cases / float(14 * spring_peak_rec[3])
  }

def write_index(regions):
  print "Write index"
  regions_by_type = dict()
  for (region_name, region_type) in regions.iterkeys():
    if region_type not in regions_by_type:
      regions_by_type[region_type] = []
    regions_by_type[region_type].append(region_name)

  regions_stats = {region: region_stats(*region) for region in regions}

  for ordering in ("index", "peak", "recent_cases", "recent_rel_spring_peak"):
    with open(os.path.join(outdir, ordering + ".html"), "w") as f:
      f.write("<html><head><style>td { padding: 3; }\n.data { text-align: center; }</style></head>\n")
      f.write("<body><h1>Covid cases in England by region</h1>\n")
      f.write('<p><a href="https://coronavirus.data.gov.uk/">Source data</a> -- <a href="https://github.com/smowton/covid-local">source code</a></p>\n')
      for (type, regions) in sorted(regions_by_type.iteritems(), key = lambda kv: len(kv[1])):
        f.write("<h2>Region type: %s</h2>\n<table>\n" % type)
        f.write('<tr><td><a href="index.html">Name</a></td><td class="data"><a href="peak.html">Peak date</a></td><td class="data"><a href="recent_cases.html">Cases last fortnight</a></td><td class="data"><a href="recent_rel_spring_peak.html">Cases last fortnight, prop. of Spring peak</a></td></tr>\n')
        sort_order = None if ordering is "index" else lambda regname: regions_stats[(regname, type)][ordering]
        for region in sorted(regions, key = sort_order, reverse = ordering != "index"):
          stats = regions_stats[(region, type)]
          f.write('<tr><td><a href="%s">%s</a></td><td class="data">%s</td><td class="data">%d</td><td class="data">%.1f%%</td></tr>\n' % \
             (escape(region + " " + type) + ".png", \
              region, \
              datetime.datetime.strftime(stats["peak"], '%Y-%m-%d'), \
              stats["recent_cases"], \
              stats["recent_rel_spring_peak"] * 100))
        f.write("</table>\n<hr/>\n")
      f.write("</body></html>")

for key, records in regions.iteritems():
  regions[key] = clean_and_add_averages(regions[key])

for (region_name, region_type), records in regions.iteritems():
  write_graph(region_name, region_type, records)

write_index(regions)
