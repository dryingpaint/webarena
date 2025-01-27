# Docker for WebArena Websites
This REAME file host the instructions for our Docker images and quick start guide for starting up websites used in WebArena.


## Shopping Website (OneStopShop)

Download the image tar from https://drive.google.com/file/d/1gxXalk9O0p9eu1YkIJcmZta1nvvyAJpA/view?usp=sharing

```
docker load --input shopping_final_0712.tar
docker run --name shopping -p 7770:80 -d shopping_final_0712
docker exec shopping /var/www/magento2/bin/magento setup:store-config:set --base-url="http://<your-server-hostname>:7770/"
docker exec shopping /var/www/magento2/bin/magento cache:flush
```
Now you can visit `http://<your-server-hostname>:7770`.


## E-commerce Content Management System (CMS)

Download the image tar from https://drive.google.com/file/d/1See0ZhJRw0WTTL9y8hFlgaduwPZ_nGfd/view?usp=sharing

```
docker load --input shopping_admin_final_0719.tar
docker run --name shopping_admin -p 7780:80 -d shopping_admin_final_0719
docker exec shopping_admin /var/www/magento2/bin/magento setup:store-config:set --base-url="http://<your-server-hostname>:7780/"
docker exec shopping_admin /var/www/magento2/bin/magento cache:flush
```
Now you can visit `http://<your-server-hostname>:7780/admin`.


## Social Forum Website (Reddit)

Download the image tar from https://drive.google.com/file/d/17Qpp1iu_mPqzgO_73Z9BnFjHrzmX9DGf/view?usp=sharing

```
docker load --input postmill-populated-exposed-withimg.tar
docker run --name forum -p 9999:80 -d postmill-populated-exposed-withimg
```
Now you can visit `http://<your-server-hostname>:9999/`.


## Gitlab Website

Download the image tar from https://drive.google.com/file/d/19W8qM0DPyRvWCLyQe0qtnCWAHGruolMR/view?usp=sharing

```
docker load --input gitlab-populated-final-port8023.tar
docker run --name gitlab -d -p 8023:8023 gitlab-populated-final-port8023 /opt/gitlab/embedded/bin/runsvdir-start
```
It might take 5 mins to start and then you can visit `http://<your-server-hostname>:8023/explore`.

## Wikipedia Website

Download the data from https://drive.google.com/file/d/1Um4QLxi_bGv5bP6kt83Ke0lNjuV9Tm0P/view?usp=sharing

```
docker run -d --name=wikipedia --volume=<your-path-to-downloaded-folder>/:/data -p 8888:80 ghcr.io/kiwix/kiwix-serve:3.3.0 wikipedia_en_all_maxi_2022-05.zim
```
Now you can visit `http://<your-server-hostname>:8888/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing`.

## Map

As the content of the map site is static, we currently host it on our server. You can set the link of the map site to `http://ec2-3-131-244-37.us-east-2.compute.amazonaws.com:3000/`. We are working on making the map site locally hostable.

## Homepage

The homepage lists all available websites which the agent can use to navigate to different sites.
![Homepage](../media/homepage_demo.png)

To host the homepage, first change `<your-server-hostname>` to the corresponding server hostnames in [webarena_homepage/index.html](webarena_homepage/index.html) and then run
```
cd webarena_homepage
flask run --host=0.0.0.0 --port=4399
```
The homepage will be available at `http://<your-server-hostname>:4399`.
