#!/bin/bash

corepack enable

yarn set version stable

yarn install 

yarn add date-fns@^4.1.0

yarn dlx @yarnpkg/sdks vscode
