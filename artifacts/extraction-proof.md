# Article Extractor Before/After Proof

*2026-03-03T21:13:48Z*

Curated 20-domain sample from Proxmox logs ( URLs), including Simon Willison and Martin Fowler examples.

```bash
wc -l artifacts/validation_urls_20_curated.txt && head -n 5 artifacts/validation_urls_20_curated.txt
```

```output
20 artifacts/validation_urls_20_curated.txt
https://simonwillison.net/guides/agentic-engineering-patterns/gif-optimization/
https://martinfowler.com/articles/reduce-friction-ai/design-first-collaboration.html
https://www.thelocal.dk/20201015/five-ways-to-make-a-good-impression-at-a-danish-home
https://leaddev.com/ai/amazon-alone-is-responsible-for-52-of-tech-layoffs-in-2026-so-far?utm_source=leaddev&utm_medium=RSS
https://www.infoworld.com/article/4125855/three-web-security-blind-spots-in-mobile-devsecops-pipelines.html
```

Before baseline was measured from /tmp/article-extractor-originmain (detached at origin/main) and saved to /tmp/before_eval_curated.json; after baseline from current working tree saved to /tmp/after_eval_curated.json.

```python
import json; b=json.load(open('/tmp/before_eval_curated.json')); a=json.load(open('/tmp/after_eval_curated.json')); print('before_success',sum(1 for r in b if r['success']),'after_success',sum(1 for r in a if r['success'])); print('before_noisy',sum(1 for r in b if r['noise_tokens']),'after_noisy',sum(1 for r in a if r['noise_tokens']))
```

```output
before_success 20 after_success 20
before_noisy 5 after_noisy 1
```

```python
import json; from urllib.parse import urlparse; b={r['url']:r for r in json.load(open('/tmp/before_eval_curated.json'))}; a={r['url']:r for r in json.load(open('/tmp/after_eval_curated.json'))}; print('reduced_noise_urls'); [print(urlparse(u).netloc,'::',u,'::',','.join(b[u]['noise_tokens'])) for u in b if b[u]['noise_tokens'] and not a[u]['noise_tokens']]; print('still_noisy_urls'); [print(urlparse(u).netloc,'::',u,'::',','.join(a[u]['noise_tokens'])) for u in b if a[u]['noise_tokens']]
```

```output
reduced_noise_urls
simonwillison.net :: https://simonwillison.net/guides/agentic-engineering-patterns/gif-optimization/ :: created:,last modified:,previous:,next:
www.theverge.com :: https://www.theverge.com/gadgets/883733/samsung-galaxy-s26-vs-plus-ultra-specs-features-hardware-comparison :: privacy policy
blog.google :: https://blog.google/innovation-and-ai/technology/ai/nano-banana-2/ :: privacy policy
beabetterdev.com :: https://beabetterdev.com/2026/03/01/ai-is-making-junior-devs-useless/ :: more from
still_noisy_urls
www.technologyreview.com :: https://www.technologyreview.com/2026/02/26/1133707/finding-value-with-ai-and-industry-5-0-transformation/ :: privacy policy
```

```bash
sed -n '1,40p' artifacts/showboat-help.txt
```

```output
showboat - Create executable demo documents that show and prove an agent's work.

Showboat helps agents build markdown documents that mix commentary, executable
code blocks, and captured output. These documents serve as both readable
documentation and reproducible proof of work. A verifier can re-execute all
code blocks and confirm the outputs still match.

Usage:
  showboat init <file> <title>             Create a new demo document
  showboat note <file> [text]              Append commentary (text or stdin)
  showboat exec <file> <lang> [code]       Run code and capture output
  showboat image <file> [script]           Run script, capture image output
  showboat pop <file>                      Remove the most recent entry
  showboat verify <file> [--output <new>]  Re-run and diff all code blocks
  showboat extract <file> [--filename <name>]  Emit commands to recreate file

Global Options:
  --workdir <dir>   Set working directory for code execution (default: current)
  --version         Print version and exit
  --help, -h        Show this help message

Exec output:
  The "exec" command prints the captured shell output to stdout and exits with
  the same exit code as the executed command. This lets agents see what happened
  and react to errors. The output is still appended to the document regardless
  of exit code. Use "pop" to remove a failed entry.

    $ showboat exec demo.md bash "echo hello && exit 1"
    hello
    $ echo $?
    1

Image:
  The "image" command runs a script that is expected to produce an image file.
  The image is saved in the same directory as the document and an image reference
  is appended to the markdown. The script is recorded as a bash code block.

Pop:
  The "pop" command removes the most recent entry from a document. For an "exec"
  or "image" entry this removes both the code block and its output. For a "note"
```
